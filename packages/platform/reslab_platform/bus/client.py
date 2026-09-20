"""Thin wrapper over nats-py with JetStream stream provisioning and typed messages."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import nats
from nats.aio.client import Client as NatsClient
from nats.aio.msg import Msg
from nats.js import JetStreamContext
from nats.js.api import (
    AckPolicy,
    ConsumerConfig,
    DeliverPolicy,
    DiscardPolicy,
    RetentionPolicy,
    StorageType,
    StreamConfig,
)
from nats.js.errors import NotFoundError
from pydantic import BaseModel, TypeAdapter

from reslab_core.protocol import (
    ArtifactMessage,
    CancelRequest,
    EventMessage,
    LifecycleMessage,
    RunFinishedMessage,
    RunJob,
    RunnerHeartbeat,
    TelemetryMessage,
)
from reslab_platform.bus.subjects import JOBS_STREAM, RUNS_STREAM, Subjects
from reslab_platform.logging import get_logger

log = get_logger(__name__)

AnyMessage = (
    RunJob
    | LifecycleMessage
    | EventMessage
    | TelemetryMessage
    | ArtifactMessage
    | RunnerHeartbeat
    | CancelRequest
    | RunFinishedMessage
)
_ADAPTER: TypeAdapter[AnyMessage] = TypeAdapter(AnyMessage)

MAX_PAYLOAD_BYTES = 8 * 1024 * 1024


def encode_message(message: BaseModel) -> bytes:
    return message.model_dump_json().encode("utf-8")


def decode_message(data: bytes) -> AnyMessage:
    if len(data) > MAX_PAYLOAD_BYTES:
        raise ValueError("message exceeds payload limit")
    return _ADAPTER.validate_json(data)


class Bus:
    def __init__(self, url: str, *, name: str = "reslab", max_age_hours: int = 48) -> None:
        self.url = url
        self.name = name
        self.max_age_hours = max_age_hours
        self._nc: NatsClient | None = None
        self._js: JetStreamContext | None = None
        self._closed = asyncio.Event()

    @property
    def nc(self) -> NatsClient:
        if self._nc is None:
            raise RuntimeError("bus not connected")
        return self._nc

    @property
    def js(self) -> JetStreamContext:
        if self._js is None:
            raise RuntimeError("bus not connected")
        return self._js

    @property
    def connected(self) -> bool:
        return self._nc is not None and self._nc.is_connected

    async def connect(self, *, ensure_streams: bool = True, timeout: float = 60.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        attempt = 0
        while True:
            attempt += 1
            try:
                self._nc = await nats.connect(
                    self.url,
                    name=self.name,
                    max_reconnect_attempts=-1,
                    reconnect_time_wait=2,
                    connect_timeout=5,
                    error_cb=self._on_error,
                    disconnected_cb=self._on_disconnected,
                    reconnected_cb=self._on_reconnected,
                )
                break
            except Exception as exc:
                if asyncio.get_running_loop().time() > deadline:
                    raise
                log.warning("nats.connect.retry", attempt=attempt, error=str(exc))
                await asyncio.sleep(min(2.0 * attempt, 10.0))
        self._js = self._nc.jetstream()
        if ensure_streams:
            await self.ensure_streams()
        log.info("nats.connected", url=self.url)

    async def _on_error(self, exc: Exception) -> None:
        log.warning("nats.error", error=str(exc))

    async def _on_disconnected(self) -> None:
        log.warning("nats.disconnected")

    async def _on_reconnected(self) -> None:
        log.info("nats.reconnected")

    async def ensure_streams(self) -> None:
        max_age = float(self.max_age_hours * 3600)
        await self._ensure_stream(
            StreamConfig(
                name=JOBS_STREAM,
                subjects=[Subjects.JOBS_WILDCARD],
                retention=RetentionPolicy.WORK_QUEUE,
                storage=StorageType.FILE,
                max_age=max_age,
                discard=DiscardPolicy.OLD,
                max_msg_size=MAX_PAYLOAD_BYTES,
            )
        )
        await self._ensure_stream(
            StreamConfig(
                name=RUNS_STREAM,
                subjects=[Subjects.RUNS_WILDCARD],
                retention=RetentionPolicy.LIMITS,
                storage=StorageType.FILE,
                max_age=max_age,
                max_bytes=2 * 1024 * 1024 * 1024,
                discard=DiscardPolicy.OLD,
                max_msg_size=MAX_PAYLOAD_BYTES,
            )
        )

    async def _ensure_stream(self, config: StreamConfig) -> None:
        try:
            await self.js.stream_info(config.name)  # type: ignore[arg-type]
            await self.js.update_stream(config)
        except NotFoundError:
            await self.js.add_stream(config)

    async def ensure_pull_consumer(
        self, stream: str, durable: str, *, filter_subject: str, ack_wait: float = 60.0
    ) -> None:
        config = ConsumerConfig(
            durable_name=durable,
            ack_policy=AckPolicy.EXPLICIT,
            deliver_policy=DeliverPolicy.ALL,
            filter_subject=filter_subject,
            ack_wait=ack_wait,
            max_ack_pending=256,
        )
        try:
            await self.js.consumer_info(stream, durable)
        except NotFoundError:
            await self.js.add_consumer(stream, config)

    async def publish_js(self, subject: str, message: BaseModel) -> None:
        payload = encode_message(message)
        if len(payload) > MAX_PAYLOAD_BYTES:
            raise ValueError(f"message on {subject} exceeds {MAX_PAYLOAD_BYTES} bytes")
        await self.js.publish(subject, payload, timeout=10.0)

    async def publish_core(self, subject: str, message: BaseModel) -> None:
        await self.nc.publish(subject, encode_message(message))

    async def subscribe_core(
        self,
        subject: str,
        handler: Callable[[AnyMessage, str], Awaitable[None]],
        *,
        queue: str = "",
    ) -> Any:
        async def _cb(msg: Msg) -> None:
            try:
                decoded = decode_message(msg.data)
            except Exception as exc:
                log.warning("nats.decode_failed", subject=msg.subject, error=str(exc))
                return
            try:
                await handler(decoded, msg.subject)
            except Exception:
                log.exception("nats.handler_failed", subject=msg.subject)

        return await self.nc.subscribe(subject, queue=queue, cb=_cb)

    async def pull_subscribe(self, subject: str, durable: str, stream: str) -> Any:
        return await self.js.pull_subscribe(subject, durable=durable, stream=stream)

    async def close(self) -> None:
        if self._nc is not None and not self._nc.is_closed:
            try:
                await self._nc.drain()
            except Exception:
                await self._nc.close()
        self._nc = None
        self._js = None

"""Application state shared by request handlers (database, bus, artifact store, live hub)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request, WebSocket
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from reslab_core.protocol import (
    ArtifactMessage,
    EventMessage,
    LifecycleMessage,
    RunFinishedMessage,
    TelemetryMessage,
)
from reslab_platform.artifacts import ArtifactStore, create_artifact_store
from reslab_platform.bus import Bus, Subjects
from reslab_platform.db import create_engine, create_session_factory
from reslab_platform.logging import get_logger
from reslab_platform.settings import PlatformSettings

log = get_logger(__name__)

LiveMessage = LifecycleMessage | EventMessage | TelemetryMessage | RunFinishedMessage


class LiveHub:
    """Fans out run messages from the bus to WebSocket subscribers, per run id."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[LiveMessage]]] = {}

    def subscribe(self, run_id: str, *, maxsize: int = 500) -> asyncio.Queue[LiveMessage]:
        queue: asyncio.Queue[LiveMessage] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.setdefault(run_id, set()).add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[LiveMessage]) -> None:
        subscribers = self._subscribers.get(run_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(run_id, None)

    def publish(self, run_id: str, message: LiveMessage) -> None:
        for queue in list(self._subscribers.get(run_id, ())):
            if queue.full():
                # Slow consumer: drop the oldest telemetry rather than block the bus.
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(message)

    @property
    def subscriber_count(self) -> int:
        return sum(len(s) for s in self._subscribers.values())


@dataclass
class AppState:
    settings: PlatformSettings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    bus: Bus
    store: ArtifactStore
    hub: LiveHub = field(default_factory=LiveHub)
    bus_subscription: Any = None
    ready: bool = False

    async def health(self) -> dict[str, bool]:
        database = False
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            database = True
        except Exception:
            database = False
        store_ok = True
        try:
            await asyncio.wait_for(self.store.ensure_ready(), timeout=5)
        except Exception:
            store_ok = False
        return {"database": database, "bus": self.bus.connected, "artifact_store": store_ok}


async def build_state(settings: PlatformSettings) -> AppState:
    engine = create_engine(settings)
    state = AppState(
        settings=settings,
        engine=engine,
        sessions=create_session_factory(engine),
        bus=Bus(settings.nats_url, name="reslab-api"),
        store=create_artifact_store(settings),
    )
    return state


async def start_state(state: AppState) -> None:
    try:
        await state.bus.connect(ensure_streams=True, timeout=120)
    except Exception as exc:
        log.error("api.bus_unavailable", error=str(exc))
    if state.bus.connected:

        async def _dispatch(message, subject: str) -> None:
            run_id = Subjects.run_id_from_subject(subject)
            if run_id and isinstance(
                message, LifecycleMessage | EventMessage | TelemetryMessage | RunFinishedMessage
            ):
                state.hub.publish(run_id, message)
            elif isinstance(message, ArtifactMessage):
                return

        state.bus_subscription = await state.bus.subscribe_core(Subjects.RUNS_WILDCARD, _dispatch)
    try:
        await state.store.ensure_ready()
    except Exception as exc:
        log.error("api.artifact_store_unavailable", error=str(exc))
    state.ready = True


async def stop_state(state: AppState) -> None:
    state.ready = False
    if state.bus_subscription is not None:
        with contextlib.suppress(Exception):
            await state.bus_subscription.unsubscribe()
    await state.bus.close()
    await state.engine.dispose()


def get_state(request: Request) -> AppState:
    return request.app.state.reslab


def get_ws_state(websocket: WebSocket) -> AppState:
    return websocket.app.state.reslab


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    state = get_state(request)
    async with state.sessions() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

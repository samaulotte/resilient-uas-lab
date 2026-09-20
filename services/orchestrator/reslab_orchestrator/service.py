"""Orchestrator: the only writer of run progress.

- consumes runner messages from the `RESLAB_RUNS` stream (durable, explicit ack);
- validates every lifecycle transition against the run state machine;
- persists events, telemetry chunks and artifacts;
- runs the analysis pipeline when a runner reports completion;
- tracks runner heartbeats and fails runs whose runner disappeared or that were never
  picked up.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from nats.errors import TimeoutError as NatsTimeoutError
from prometheus_client import Counter, Gauge
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reslab_core.ids import validate_artifact_name
from reslab_core.protocol import (
    ArtifactMessage,
    CancelRequest,
    EventMessage,
    LifecycleMessage,
    RunFinishedMessage,
    RunnerHeartbeat,
    TelemetryMessage,
)
from reslab_core.states import InvalidRunTransitionError, RunState
from reslab_orchestrator.analysis import analyze_run
from reslab_platform.artifacts import ArtifactStore, create_artifact_store
from reslab_platform.bus import Bus, Subjects, decode_message
from reslab_platform.bus.subjects import ORCHESTRATOR_CONSUMER, RUNS_STREAM
from reslab_platform.db import Run, create_engine, create_session_factory, repository, session_scope
from reslab_platform.logging import get_logger
from reslab_platform.settings import PlatformSettings

log = get_logger(__name__)

MESSAGES = Counter("reslab_orchestrator_messages_total", "Bus messages processed", ["type"])
RUNS_COMPLETED = Counter("reslab_orchestrator_runs_finalized_total", "Runs finalized", ["state"])
ACTIVE_RUNS = Gauge("reslab_orchestrator_active_runs", "Runs in a non-terminal state")
# Container-local liveness marker on a private tmpfs (see infra/docker/healthcheck.py).
HEALTH_FILE = Path("/tmp/reslab-orchestrator-healthy")  # noqa: S108  # nosec B108


class OrchestratorService:
    def __init__(self, settings: PlatformSettings) -> None:
        self.settings = settings
        self.bus = Bus(settings.nats_url, name="reslab-orchestrator")
        self.engine = create_engine(settings)
        self.sessions: async_sessionmaker[AsyncSession] = create_session_factory(self.engine)
        self.store: ArtifactStore = create_artifact_store(settings)
        self._stop = asyncio.Event()
        self._started_at = datetime.now(tz=UTC)

    # ------------------------------------------------------------------ lifecycle

    async def run_forever(self) -> None:
        await self.store.ensure_ready()
        await self.bus.connect()
        await self.bus.ensure_pull_consumer(
            RUNS_STREAM,
            ORCHESTRATOR_CONSUMER,
            filter_subject=Subjects.RUNS_WILDCARD,
            ack_wait=120.0,
        )
        heartbeat_sub = await self.bus.subscribe_core(Subjects.RUNNER_HEARTBEAT, self._on_heartbeat)
        watchdog = asyncio.create_task(self._watchdog_loop(), name="orchestrator-watchdog")
        log.info("orchestrator.started", artifacts=self.store.describe())
        try:
            await self._consume_loop()
        finally:
            watchdog.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watchdog
            with contextlib.suppress(Exception):
                await heartbeat_sub.unsubscribe()
            await self.bus.close()
            await self.engine.dispose()

    def request_stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ consumption

    async def _consume_loop(self) -> None:
        subscription = await self.bus.pull_subscribe(
            Subjects.RUNS_WILDCARD, ORCHESTRATOR_CONSUMER, RUNS_STREAM
        )
        while not self._stop.is_set():
            try:
                messages = await subscription.fetch(50, timeout=2)
            except NatsTimeoutError:
                HEALTH_FILE.write_text(datetime.now(tz=UTC).isoformat())
                continue
            except Exception:
                log.exception("orchestrator.fetch_failed")
                await asyncio.sleep(1.0)
                continue
            for msg in messages:
                try:
                    message = decode_message(msg.data)
                except Exception as exc:
                    log.warning("orchestrator.undecodable", subject=msg.subject, error=str(exc))
                    await msg.term()
                    continue
                try:
                    await self.handle(message)
                    await msg.ack()
                except Exception:
                    log.exception("orchestrator.handle_failed", subject=msg.subject)
                    # Persisted messages are retried a bounded number of times.
                    if msg.metadata.num_delivered >= 5:
                        await msg.term()
                    else:
                        await msg.nak(delay=2)
            HEALTH_FILE.write_text(datetime.now(tz=UTC).isoformat())

    async def handle(self, message) -> None:
        MESSAGES.labels(type=getattr(message, "type", "unknown")).inc()
        if isinstance(message, LifecycleMessage):
            await self._on_lifecycle(message)
        elif isinstance(message, EventMessage):
            await self._on_event(message)
        elif isinstance(message, TelemetryMessage):
            await self._on_telemetry(message)
        elif isinstance(message, ArtifactMessage):
            await self._on_artifact(message)
        elif isinstance(message, RunFinishedMessage):
            await self._on_finished(message)
        elif isinstance(message, RunnerHeartbeat):
            await self._on_heartbeat(message, Subjects.RUNNER_HEARTBEAT)
        else:
            log.debug("orchestrator.ignored", type=type(message).__name__)

    # ------------------------------------------------------------------ handlers

    async def _on_lifecycle(self, message: LifecycleMessage) -> None:
        async with session_scope(self.sessions) as session:
            run = await repository.get_run(session, message.run_id)
            if run is None:
                log.warning("lifecycle.unknown_run", run_id=message.run_id)
                return
            current = RunState(run.state)
            if current.is_terminal:
                if current is RunState.CANCELLED and message.state in (
                    RunState.PREPARING,
                    RunState.RUNNING,
                ):
                    # A runner picked up a run cancelled while queued: tell it to stop.
                    await self.bus.publish_core(
                        Subjects.control_cancel(message.run_id),
                        CancelRequest(run_id=message.run_id, reason="run was cancelled"),
                    )
                log.info(
                    "lifecycle.ignored_terminal", run_id=message.run_id, state=message.state.value
                )
                return
            fields: dict = {"runner_id": message.runner_id}
            if message.planned_path is not None:
                fields["planned_path"] = message.planned_path.model_dump(mode="json")
            if message.simulation_time:
                fields["last_simulation_time"] = message.simulation_time
            provenance = dict(run.provenance or {})
            changed = False
            if message.adapter_version and not provenance.get("adapter_version"):
                provenance["adapter_version"] = message.adapter_version
                changed = True
            if message.data_origin and provenance.get("data_origin") != message.data_origin:
                provenance["data_origin"] = message.data_origin
                changed = True
            if message.runner_id and provenance.get("runner_id") != message.runner_id:
                provenance["runner_id"] = message.runner_id
                changed = True
            if changed:
                fields["provenance"] = provenance
            try:
                await repository.transition_run(
                    session, run, message.state, reason=message.reason or None, **fields
                )
            except InvalidRunTransitionError as exc:
                log.warning("lifecycle.invalid_transition", run_id=message.run_id, error=str(exc))

    async def _on_event(self, message: EventMessage) -> None:
        async with session_scope(self.sessions) as session:
            inserted = await repository.insert_events(session, [message.event])
            if inserted:
                await repository.update_run_fields(
                    session,
                    message.run_id,
                    event_count=Run.event_count + 1,
                    last_simulation_time=message.event.simulation_time,
                )

    async def _on_telemetry(self, message: TelemetryMessage) -> None:
        async with session_scope(self.sessions) as session:
            inserted = await repository.insert_telemetry_chunk(
                session, message.run_id, message.sequence, message.samples
            )
            if inserted:
                await repository.update_run_fields(
                    session,
                    message.run_id,
                    sample_count=Run.sample_count + len(message.samples),
                    last_simulation_time=message.samples[-1].t,
                )

    async def _on_artifact(self, message: ArtifactMessage) -> None:
        name = validate_artifact_name(message.name)
        data = base64.b64decode(message.data_base64, validate=True)
        async with session_scope(self.sessions) as session:
            run = await repository.get_run(session, message.run_id)
            if run is None:
                return
            stored = await self.store.put(message.run_id, name, data, message.content_type)
            await repository.upsert_artifact(
                session,
                message.run_id,
                name=name,
                content_type=message.content_type,
                size_bytes=stored.size_bytes,
                storage_key=stored.key,
                sha256=stored.sha256,
                description=message.description,
            )

    async def _on_finished(self, message: RunFinishedMessage) -> None:
        async with session_scope(self.sessions) as session:
            run = await repository.get_run(session, message.run_id)
            if run is None:
                log.warning("finished.unknown_run", run_id=message.run_id)
                return
            await self.finalize(session, run, outcome=message.outcome, reason=message.reason)

    async def finalize(self, session: AsyncSession, run: Run, *, outcome: str, reason: str) -> None:
        current = RunState(run.state)
        if current.is_terminal:
            log.info("finalize.already_terminal", run_id=str(run.id), state=current.value)
            return
        run_id = str(run.id)
        # Make sure we are in COLLECTING before analysis; runners always send it, but a
        # lost message must not block finalization.
        if current in (RunState.PREPARING, RunState.RUNNING, RunState.RECOVERING, RunState.QUEUED):
            if current is RunState.QUEUED:
                await repository.transition_run(session, run, RunState.PREPARING)
                await repository.transition_run(session, run, RunState.RUNNING)
            elif current is RunState.PREPARING:
                await repository.transition_run(session, run, RunState.RUNNING)
            await repository.transition_run(session, run, RunState.COLLECTING)

        if outcome == "completed":
            await repository.transition_run(session, run, RunState.ANALYZING, reason="analysis")
            await session.flush()
            try:
                report = await analyze_run(
                    session, self.store, run, final_state=RunState.COMPLETED, reason=reason
                )
                await repository.transition_run(
                    session, run, RunState.COMPLETED, reason=report.score.reason
                )
                RUNS_COMPLETED.labels(state="COMPLETED").inc()
            except Exception as exc:
                log.exception("finalize.analysis_failed", run_id=run_id)
                await repository.transition_run(
                    session, run, RunState.FAILED, reason=f"analysis failed: {exc}"[:500]
                )
                RUNS_COMPLETED.labels(state="FAILED").inc()
            return

        final = RunState.CANCELLED if outcome == "cancelled" else RunState.FAILED
        # Best effort report for diagnostics (inconclusive result), never blocking.
        try:
            await analyze_run(session, self.store, run, final_state=final, reason=reason)
        except Exception as exc:
            log.warning("finalize.partial_report_failed", run_id=run_id, error=str(exc))
        await repository.transition_run(session, run, final, reason=reason or final.value.lower())
        RUNS_COMPLETED.labels(state=final.value).inc()

    async def _on_heartbeat(self, message, subject: str) -> None:
        if not isinstance(message, RunnerHeartbeat):
            return
        async with session_scope(self.sessions) as session:
            await repository.upsert_runner(
                session,
                runner_id=message.runner_id,
                adapters=message.adapters,
                version=message.version,
                active_run_id=message.active_run_id,
                seen_at=datetime.now(tz=UTC),
            )

    # ------------------------------------------------------------------ watchdog

    async def _watchdog_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._watchdog_tick()
            except Exception:
                log.exception("watchdog.failed")
            await asyncio.sleep(self.settings.orchestrator_watchdog_seconds)

    async def _watchdog_tick(self) -> None:
        now = datetime.now(tz=UTC)
        stale_after = timedelta(seconds=self.settings.runner_stale_after_seconds)
        queued_timeout = timedelta(seconds=self.settings.queued_timeout_seconds)
        # Grace period after start: runner heartbeats may not have been observed yet.
        heartbeats_trusted = now - self._started_at > stale_after
        async with session_scope(self.sessions) as session:
            runners = {r.runner_id: r for r in await repository.list_runners(session)}
            active = await repository.list_active_runs(session)
            ACTIVE_RUNS.set(len(active))
            for run in active:
                state = RunState(run.state)
                if state in (RunState.CREATED, RunState.VALIDATING):
                    continue
                if state is RunState.QUEUED:
                    if now - run.created_at > queued_timeout:
                        await repository.transition_run(
                            session,
                            run,
                            RunState.FAILED,
                            reason=(
                                f"no runner accepted the job within "
                                f"{int(queued_timeout.total_seconds())}s "
                                f"(adapter '{run.adapter}')"
                            ),
                        )
                        log.warning("watchdog.queued_timeout", run_id=str(run.id))
                    continue
                if state is RunState.ANALYZING:
                    continue
                # A run that keeps producing messages is alive whatever the heartbeat says.
                last_progress = max(filter(None, (run.updated_at, run.started_at, run.created_at)))
                if now - last_progress <= stale_after or not heartbeats_trusted:
                    continue
                runner = runners.get(run.runner_id or "")
                if runner is None:
                    await self.finalize(
                        session, run, outcome="failed", reason="runner unknown or vanished"
                    )
                    log.warning("watchdog.runner_unknown", run_id=str(run.id))
                    continue
                if now - runner.last_heartbeat_at > stale_after:
                    await self.finalize(
                        session,
                        run,
                        outcome="failed",
                        reason=f"runner '{runner.runner_id}' stopped sending heartbeats",
                    )
                    log.warning(
                        "watchdog.runner_stale", run_id=str(run.id), runner=runner.runner_id
                    )

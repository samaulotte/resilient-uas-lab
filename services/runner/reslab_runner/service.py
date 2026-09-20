"""Runner service: pulls jobs from the work queue and executes scenarios.

Execution is at-most-once: the job is acknowledged as soon as a runner accepts it.
If a runner dies mid-run the orchestrator's watchdog fails the run once heartbeats
stop, which is preferable to silently re-running a scenario that may already have
produced telemetry.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import time
from pathlib import Path

from nats.errors import TimeoutError as NatsTimeoutError
from prometheus_client import Counter, Gauge

from reslab_core.engine import CancelToken, ScenarioEngine
from reslab_core.protocol import (
    MAX_ARTIFACT_MESSAGE_BYTES,
    ArtifactMessage,
    CancelRequest,
    RunFinishedMessage,
    RunJob,
    RunnerHeartbeat,
)
from reslab_core.scenario import ScenarioValidationError, load_scenario
from reslab_core.states import RunState
from reslab_core.versions import SOFTWARE_VERSION
from reslab_platform.bus import Bus, Subjects
from reslab_platform.bus.subjects import JOBS_CONSUMER, JOBS_STREAM
from reslab_platform.logging import get_logger
from reslab_platform.settings import PlatformSettings
from reslab_runner.adapters import capabilities_for, create_adapter
from reslab_runner.sink import BusSink

log = get_logger(__name__)

RUNS_STARTED = Counter("reslab_runner_runs_started_total", "Runs started by this runner")
RUNS_FINISHED = Counter(
    "reslab_runner_runs_finished_total", "Runs finished by this runner", ["outcome"]
)
ACTIVE_RUNS = Gauge("reslab_runner_active_runs", "Runs currently executing")
# Container-local liveness marker on a private tmpfs (see infra/docker/healthcheck.py).
HEALTH_FILE = Path("/tmp/reslab-runner-healthy")  # noqa: S108  # nosec B108


class RunnerService:
    def __init__(self, settings: PlatformSettings) -> None:
        self.settings = settings
        self.runner_id = settings.runner_id
        self.adapters = settings.runner_adapter_list
        self.bus = Bus(settings.nats_url, name=f"reslab-runner-{self.runner_id}")
        self._stop = asyncio.Event()
        self._active: dict[str, CancelToken] = {}
        self._semaphore = asyncio.Semaphore(settings.runner_concurrency)

    # ------------------------------------------------------------------ lifecycle

    async def run_forever(self) -> None:
        await self.bus.connect()
        await self.bus.ensure_pull_consumer(
            JOBS_STREAM, JOBS_CONSUMER, filter_subject=Subjects.JOBS_RUN, ack_wait=30.0
        )
        control = await self.bus.subscribe_core(Subjects.CONTROL_WILDCARD, self._on_control)
        heartbeat = asyncio.create_task(self._heartbeat_loop(), name="runner-heartbeat")
        log.info("runner.started", runner_id=self.runner_id, adapters=self.adapters)
        try:
            await self._job_loop()
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
            with contextlib.suppress(Exception):
                await control.unsubscribe()
            await self.bus.close()

    def request_stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ loops

    async def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            try:
                active = next(iter(self._active), None)
                await self.bus.publish_core(
                    Subjects.RUNNER_HEARTBEAT,
                    RunnerHeartbeat(
                        runner_id=self.runner_id,
                        adapters=self.adapters,
                        active_run_id=active,
                        version=SOFTWARE_VERSION,
                    ),
                )
                HEALTH_FILE.write_text(str(time.time()))
            except Exception as exc:
                log.warning("runner.heartbeat_failed", error=str(exc))
            await asyncio.sleep(self.settings.runner_heartbeat_seconds)

    async def _on_control(self, message, subject: str) -> None:
        if isinstance(message, CancelRequest):
            token = self._active.get(message.run_id)
            if token is not None:
                log.info("runner.cancel_received", run_id=message.run_id, reason=message.reason)
                token.cancel(message.reason)

    async def _job_loop(self) -> None:
        subscription = await self.bus.pull_subscribe(Subjects.JOBS_RUN, JOBS_CONSUMER, JOBS_STREAM)
        tasks: set[asyncio.Task[None]] = set()
        while not self._stop.is_set():
            await self._semaphore.acquire()
            released = False
            try:
                try:
                    messages = await subscription.fetch(1, timeout=5)
                except NatsTimeoutError:
                    self._semaphore.release()
                    released = True
                    continue
                for msg in messages:
                    try:
                        job = RunJob.model_validate_json(msg.data)
                    except Exception as exc:
                        log.error("runner.invalid_job", error=str(exc))
                        await msg.term()
                        self._semaphore.release()
                        released = True
                        continue
                    if job.adapter not in self.adapters:
                        # Another runner may offer this adapter; hand the job back.
                        await msg.nak(delay=5)
                        self._semaphore.release()
                        released = True
                        continue
                    await msg.ack()
                    task = asyncio.create_task(
                        self._execute_and_release(job), name=f"run-{job.run_id}"
                    )
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                    released = True
            except Exception:
                log.exception("runner.job_loop_error")
                if not released:
                    self._semaphore.release()
                await asyncio.sleep(1.0)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_and_release(self, job: RunJob) -> None:
        try:
            await self.execute(job)
        finally:
            self._semaphore.release()

    # ------------------------------------------------------------------ execution

    async def execute(self, job: RunJob) -> RunFinishedMessage:
        run_id = job.run_id
        token = CancelToken()
        self._active[run_id] = token
        ACTIVE_RUNS.inc()
        RUNS_STARTED.inc()
        log.info("run.accepted", run_id=run_id, adapter=job.adapter, seed=job.seed, speed=job.speed)
        outcome = "failed"
        reason = ""
        result = None
        sink: BusSink | None = None
        try:
            scenario = load_scenario(job.scenario_yaml)
            adapter = create_adapter(job, self.settings)
            capabilities = capabilities_for(job.adapter)
            sink = BusSink(
                self.bus,
                run_id=run_id,
                runner_id=self.runner_id,
                adapter_version=getattr(adapter, "version", None),
                data_origin=capabilities.data_origin if capabilities else None,
            )
            engine = ScenarioEngine(
                run_id=run_id,
                scenario=scenario,
                adapter=adapter,
                sink=sink,
                seed=job.seed,
                speed=job.speed,
                cancel_token=token,
            )
            result = await engine.run()
            for blob in result.artifacts:
                await self._publish_artifact(run_id, blob)
            if result.final_state is RunState.COLLECTING:
                outcome = "completed"
            elif result.final_state is RunState.CANCELLED:
                outcome = "cancelled"
            else:
                outcome = "failed"
            reason = result.reason
        except ScenarioValidationError as exc:
            reason = f"scenario rejected by runner: {exc}"
            log.error("run.invalid_scenario", run_id=run_id, error=str(exc))
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            log.exception("run.execution_failed", run_id=run_id)
        finally:
            self._active.pop(run_id, None)
            ACTIVE_RUNS.dec()
        finished = RunFinishedMessage(
            run_id=run_id,
            outcome=outcome,  # type: ignore[arg-type]
            reason=reason,
            runner_id=self.runner_id,
            simulation_time=result.simulation_time if result else 0.0,
            event_count=result.event_count if result else (sink.event_count if sink else 0),
            sample_count=result.sample_count if result else (sink.sample_count if sink else 0),
            mission_complete=result.mission_complete if result else False,
            final_component_states=(
                {k: v.value for k, v in result.final_component_states.items()} if result else {}
            ),
        )
        try:
            await self.bus.publish_js(Subjects.run_finished(run_id), finished)
        except Exception:
            log.exception("run.finished_publish_failed", run_id=run_id)
        RUNS_FINISHED.labels(outcome=outcome).inc()
        log.info("run.finished", run_id=run_id, outcome=outcome, reason=reason)
        return finished

    async def _publish_artifact(self, run_id: str, blob) -> None:
        if len(blob.data) > MAX_ARTIFACT_MESSAGE_BYTES:
            log.warning(
                "run.artifact_too_large", run_id=run_id, name=blob.name, size=len(blob.data)
            )
            return
        await self.bus.publish_js(
            Subjects.run_artifacts(run_id),
            ArtifactMessage(
                run_id=run_id,
                name=blob.name,
                content_type=blob.content_type,
                description=blob.description,
                data_base64=base64.b64encode(blob.data).decode("ascii"),
            ),
        )

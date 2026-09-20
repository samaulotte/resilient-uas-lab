"""The scenario engine.

Responsibilities:

- schedule scenario events on the simulation clock reported by the adapter;
- request injections and record whether the adapter applied them;
- clear bounded injections when their duration elapses;
- classify every observed change (observed effect, system response, recovery);
- verify declared expectations against observations;
- batch telemetry for the sink;
- enforce the mission timeout and cancellation.

The engine does not know what the target is. It only speaks the adapter contract.
"""

from __future__ import annotations

import asyncio
import contextlib
import heapq
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from reslab_core.adapter import (
    AdapterConfiguration,
    ArtifactBlob,
    AutonomousSystemAdapter,
    ClearRequest,
    InjectionRequest,
)
from reslab_core.duration import parse_duration
from reslab_core.scenario.catalog import TRANSIENT_EFFECTS
from reslab_core.scenario.model import Expectation, ResilienceScenario, ScenarioEvent
from reslab_core.states import (
    ComponentState,
    EventKind,
    EventSource,
    MissionPhase,
    RunState,
    Severity,
)
from reslab_core.telemetry import PlannedPath, RunEvent, TelemetrySample, utcnow
from reslab_core.topology import DEFAULT_TOPOLOGY, SystemTopology


class EngineSink(Protocol):
    async def on_lifecycle(
        self,
        state: RunState,
        *,
        reason: str = "",
        simulation_time: float = 0.0,
        planned_path: PlannedPath | None = None,
    ) -> None: ...

    async def on_event(self, event: RunEvent) -> None: ...

    async def on_telemetry(self, samples: list[TelemetrySample]) -> None: ...


T = TypeVar("T")


class CancelToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()
        self.reason = ""

    def cancel(self, reason: str = "cancelled") -> None:
        self.reason = reason
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()


class _PreparationCancelledError(Exception):
    """Raised internally when a cancel request arrives while the adapter prepares."""


class UnsupportedInjectionError(Exception):
    def __init__(self, items: list[str]) -> None:
        self.items = items
        super().__init__("adapter does not support: " + ", ".join(items))


class EngineResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    final_state: RunState
    reason: str = ""
    simulation_time: float
    event_count: int
    sample_count: int
    final_component_states: dict[str, ComponentState]
    planned_path: PlannedPath | None
    artifacts: list[ArtifactBlob] = Field(default_factory=list)
    mission_complete: bool


@dataclass(order=True)
class _ScheduledClear:
    at: float
    event_id: str = field(compare=False)
    request: InjectionRequest = field(compare=False)


@dataclass
class _PendingExpectation:
    scenario_event_id: str
    expectation: Expectation
    deadline: float
    requested_at: float
    left_healthy: bool = False


_SEVERITY_FOR_STATE: dict[ComponentState, Severity] = {
    ComponentState.DEGRADED: Severity.MEDIUM,
    ComponentState.UNAVAILABLE: Severity.HIGH,
    ComponentState.RECOVERING: Severity.HIGH,
    ComponentState.FAILED: Severity.CRITICAL,
}


class ScenarioEngine:
    def __init__(
        self,
        *,
        run_id: str,
        scenario: ResilienceScenario,
        adapter: AutonomousSystemAdapter,
        sink: EngineSink,
        seed: int | None = None,
        speed: float | None = None,
        topology: SystemTopology = DEFAULT_TOPOLOGY,
        cancel_token: CancelToken | None = None,
        telemetry_batch_seconds: float = 0.5,
        on_run_state: Callable[[RunState], Awaitable[None]] | None = None,
    ) -> None:
        self.run_id = run_id
        self.scenario = scenario
        self.adapter = adapter
        self.sink = sink
        self.topology = topology
        self.cancel_token = cancel_token or CancelToken()
        self.seed = scenario.simulation.seed if seed is None else seed
        self.speed = scenario.simulation.speed if speed is None else speed
        self.telemetry_batch_seconds = telemetry_batch_seconds
        self._on_run_state = on_run_state

        self._sequence = 0
        self._sample_count = 0
        self._states: dict[str, ComponentState] = {}
        self._fault_open_since: dict[str, float] = {}
        self._active: dict[str, InjectionRequest] = {}
        self._clears: list[_ScheduledClear] = []
        self._expectations: list[_PendingExpectation] = []
        self._pending_events: list[ScenarioEvent] = []
        self._batch: list[TelemetrySample] = []
        self._batch_started_at: float | None = None
        self._run_state = RunState.QUEUED
        self._planned_path: PlannedPath | None = None
        self._last_t = 0.0

    # ------------------------------------------------------------------ helpers

    async def _emit(
        self,
        *,
        t: float,
        kind: EventKind,
        event_type: str,
        message: str,
        source: EventSource = EventSource.ENGINE,
        severity: Severity = Severity.INFO,
        subsystem: str | None = None,
        state_before: ComponentState | None = None,
        state_after: ComponentState | None = None,
        scenario_event_id: str | None = None,
        metadata: dict | None = None,
    ) -> RunEvent:
        event = RunEvent(
            run_id=self.run_id,
            sequence=self._sequence,
            simulation_time=round(t, 3),
            wall_time=utcnow(),
            source=source,
            kind=kind,
            event_type=event_type,
            severity=severity,
            subsystem=subsystem,
            state_before=state_before,
            state_after=state_after,
            message=message[:500],
            scenario_event_id=scenario_event_id,
            metadata=metadata or {},
        )
        self._sequence += 1
        await self.sink.on_event(event)
        return event

    async def _set_run_state(self, state: RunState, *, reason: str = "", t: float = 0.0) -> None:
        if state == self._run_state:
            return
        self._run_state = state
        await self.sink.on_lifecycle(
            state, reason=reason, simulation_time=t, planned_path=self._planned_path
        )
        if self._on_run_state is not None:
            await self._on_run_state(state)

    def _component_name(self, subsystem: str) -> str:
        try:
            return self.topology.component(subsystem).name
        except KeyError:
            return subsystem

    def _check_support(self) -> None:
        unsupported = [
            f"{e.inject.subsystem}:{e.inject.effect.value} (event '{e.id}')"
            for e in self.scenario.expanded_events()
            if not self.adapter.capabilities.supports(e.inject.subsystem, e.inject.effect)
        ]
        if unsupported:
            raise UnsupportedInjectionError(unsupported)

    # ------------------------------------------------------------------ main loop

    async def run(self) -> EngineResult:
        scenario = self.scenario
        timeout = scenario.mission.timeout_seconds
        self._pending_events = scenario.expanded_events()
        final_state = RunState.COLLECTING
        reason = ""
        mission_complete = False
        artifacts: list[ArtifactBlob] = []

        try:
            await self._set_run_state(RunState.PREPARING, reason="preparing target")
            self._check_support()
            configuration = AdapterConfiguration(
                run_id=self.run_id,
                target=scenario.target,
                mission=scenario.mission,
                recovery=scenario.recovery,
                simulation=scenario.simulation.model_copy(
                    update={"seed": self.seed, "speed": self.speed}
                ),
                topology=self.topology,
            )
            self._planned_path = await self._cancellable(self.adapter.prepare(configuration))
            health = await self.adapter.health()
            self._states = dict(health.states)

            await self._set_run_state(RunState.RUNNING, reason="mission started")
            await self._emit(
                t=0.0,
                kind=EventKind.MISSION,
                event_type="mission_started",
                message=f"Mission '{scenario.metadata.name}' started on adapter "
                f"'{self.adapter.capabilities.name}'",
                source=EventSource.ENGINE,
                metadata={"seed": self.seed, "speed": self.speed},
            )
            await self.adapter.start()

            async for observation in self.adapter.observe():
                sample = observation.sample
                t = sample.t
                self._last_t = t

                if self.cancel_token.cancelled:
                    final_state = RunState.CANCELLED
                    reason = self.cancel_token.reason or "cancelled"
                    await self._emit(
                        t=t,
                        kind=EventKind.LIFECYCLE,
                        event_type="run_cancelled",
                        message=f"Run cancelled: {reason}",
                        severity=Severity.MEDIUM,
                    )
                    break

                await self._process_scheduled(t)
                await self._process_observation(observation)
                await self._process_expectations(t)
                await self._buffer_sample(sample)

                if observation.finished:
                    mission_complete = sample.mission.phase is MissionPhase.COMPLETE
                    await self._emit(
                        t=t,
                        kind=EventKind.MISSION,
                        event_type="mission_complete" if mission_complete else "mission_ended",
                        message="Mission complete" if mission_complete else "Mission ended",
                        severity=Severity.INFO if mission_complete else Severity.MEDIUM,
                        metadata={"progress": sample.mission.progress},
                    )
                    break

                if t >= timeout:
                    await self._emit(
                        t=t,
                        kind=EventKind.MISSION,
                        event_type="mission_timeout",
                        message=f"Mission timeout reached ({scenario.mission.timeout})",
                        severity=Severity.HIGH,
                        metadata={"progress": sample.mission.progress},
                    )
                    break

            await self._flush_expectations_at_end(self._last_t)
            await self._clear_all(self._last_t, reason="scenario end")
            await self._flush_batch(force=True)

        except UnsupportedInjectionError as exc:
            final_state = RunState.FAILED
            reason = str(exc)
            await self._emit(
                t=0.0,
                kind=EventKind.INJECTION_REJECTED,
                event_type="unsupported_injection",
                message=reason,
                severity=Severity.CRITICAL,
                metadata={"unsupported": exc.items},
            )
        except _PreparationCancelledError:
            final_state = RunState.CANCELLED
            reason = self.cancel_token.reason or "cancelled"
            await self._emit(
                t=0.0,
                kind=EventKind.LIFECYCLE,
                event_type="run_cancelled",
                message=f"Run cancelled during preparation: {reason}",
                source=EventSource.ENGINE,
            )
        except asyncio.CancelledError:
            final_state = RunState.CANCELLED
            reason = "runner interrupted"
            raise
        except Exception as exc:
            final_state = RunState.FAILED
            reason = f"{type(exc).__name__}: {exc}"
            await self._emit(
                t=self._last_t,
                kind=EventKind.LIFECYCLE,
                event_type="target_failure",
                message=f"Target failure: {reason}"[:500],
                severity=Severity.CRITICAL,
            )
        finally:
            await self._flush_batch(force=True)
            try:
                await self._set_run_state(
                    RunState.COLLECTING, reason="collecting artifacts", t=self._last_t
                )
                artifacts = await self.adapter.collect_artifacts()
            except Exception as exc:
                await self._emit(
                    t=self._last_t,
                    kind=EventKind.LOG,
                    event_type="artifact_collection_failed",
                    message=f"Artifact collection failed: {exc}"[:500],
                    severity=Severity.MEDIUM,
                )
            try:
                await self.adapter.stop()
            except Exception as exc:
                await self._emit(
                    t=self._last_t,
                    kind=EventKind.LOG,
                    event_type="adapter_stop_failed",
                    message=f"Adapter stop failed: {exc}"[:500],
                    severity=Severity.LOW,
                )

        return EngineResult(
            final_state=final_state,
            reason=reason,
            simulation_time=self._last_t,
            event_count=self._sequence,
            sample_count=self._sample_count,
            final_component_states=dict(self._states),
            planned_path=self._planned_path,
            artifacts=artifacts,
            mission_complete=mission_complete,
        )

    async def _cancellable(self, awaitable: Awaitable[T]) -> T:
        """Await `awaitable` unless the cancel token fires first.

        Adapter preparation can take long (connecting to a simulator); a cancel request
        must interrupt it instead of waiting for the adapter's own timeout.
        """
        work = asyncio.ensure_future(awaitable)
        cancel = asyncio.ensure_future(self.cancel_token.wait())
        try:
            done, _ = await asyncio.wait({work, cancel}, return_when=asyncio.FIRST_COMPLETED)
            if work in done:
                return work.result()
            work.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await work
            raise _PreparationCancelledError
        finally:
            cancel.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cancel

    # ------------------------------------------------------------------ scheduling

    async def _process_scheduled(self, t: float) -> None:
        while self._pending_events and self._pending_events[0].at_seconds <= t:
            event = self._pending_events.pop(0)
            await self._inject(event, t)
        while self._clears and self._clears[0].at <= t:
            scheduled = heapq.heappop(self._clears)
            await self._clear(scheduled.request, t, reason="duration elapsed")

    async def _inject(self, event: ScenarioEvent, t: float) -> None:
        inject = event.inject
        parameters = {k: v for k, v in inject.parameters.items()}
        request = InjectionRequest(
            scenario_event_id=event.id,
            subsystem=inject.subsystem,
            effect=inject.effect,
            duration=inject.duration_seconds,
            parameters=parameters,
        )
        name = self._component_name(inject.subsystem)
        await self._emit(
            t=t,
            kind=EventKind.INJECTION_REQUEST,
            event_type="injection_requested",
            message=f"Inject '{inject.effect.value}' into {name}",
            source=EventSource.SCENARIO,
            severity=Severity.INFO,
            subsystem=inject.subsystem,
            scenario_event_id=event.id,
            metadata={
                "effect": inject.effect.value,
                "duration": inject.duration,
                "parameters": parameters,
                "scheduled_at": event.at,
            },
        )
        result = await self.adapter.inject(request)
        if result.applied:
            self._active[event.id] = request
            if request.duration is not None:
                heapq.heappush(
                    self._clears,
                    _ScheduledClear(at=t + request.duration, event_id=event.id, request=request),
                )
            await self._emit(
                t=t,
                kind=EventKind.INJECTION_APPLIED,
                event_type="injection_applied",
                message=f"{name}: '{inject.effect.value}' applied via {result.mechanism}",
                source=EventSource.ADAPTER,
                severity=Severity.INFO,
                subsystem=inject.subsystem,
                scenario_event_id=event.id,
                metadata={"mechanism": result.mechanism, "detail": result.detail},
            )
            for expectation in event.expect:
                self._expectations.append(
                    _PendingExpectation(
                        scenario_event_id=event.id,
                        expectation=expectation,
                        deadline=t + expectation.within_seconds,
                        requested_at=t,
                    )
                )
        else:
            await self._emit(
                t=t,
                kind=EventKind.INJECTION_REJECTED,
                event_type="injection_rejected",
                message=f"{name}: '{inject.effect.value}' rejected: {result.detail}",
                source=EventSource.ADAPTER,
                severity=Severity.HIGH,
                subsystem=inject.subsystem,
                scenario_event_id=event.id,
                metadata={"mechanism": result.mechanism, "detail": result.detail},
            )

    async def _clear(self, request: InjectionRequest, t: float, *, reason: str) -> None:
        if request.scenario_event_id not in self._active:
            return
        result = await self.adapter.clear(
            ClearRequest(
                scenario_event_id=request.scenario_event_id,
                subsystem=request.subsystem,
                effect=request.effect,
            )
        )
        del self._active[request.scenario_event_id]
        await self._emit(
            t=t,
            kind=EventKind.INJECTION_CLEARED,
            event_type="injection_cleared",
            message=f"{self._component_name(request.subsystem)}: '{request.effect.value}' "
            f"cleared ({reason})",
            source=EventSource.SCENARIO,
            subsystem=request.subsystem,
            scenario_event_id=request.scenario_event_id,
            metadata={"reason": reason, "applied": result.applied, "mechanism": result.mechanism},
        )

    async def _clear_all(self, t: float, *, reason: str) -> None:
        for request in list(self._active.values()):
            # Transient effects clear themselves; only persistent ones are cleared here.
            if request.duration is None and request.effect not in TRANSIENT_EFFECTS:
                await self._clear(request, t, reason=reason)
            elif request.effect in TRANSIENT_EFFECTS:
                del self._active[request.scenario_event_id]
        self._clears.clear()

    # ------------------------------------------------------------------ observations

    def _attribute_cause(self, subsystem: str) -> str | None:
        """Best-effort attribution of a state change to an active scenario event.

        Direct: an active injection targets this subsystem. Indirect: an active
        injection targets an upstream provider (propagation). Returns None when the
        change cannot be attributed, which the analysis treats as an independent or
        propagated fault.
        """

        for event_id, request in self._active.items():
            if request.subsystem == subsystem:
                return event_id
        upstream = set(self.topology.upstream(subsystem))
        for event_id, request in self._active.items():
            if request.subsystem in upstream:
                return event_id
        return None

    async def _process_observation(self, observation) -> None:
        t = observation.sample.t
        for change in observation.state_changes:
            before = self._states.get(change.subsystem, ComponentState.UNKNOWN)
            after = change.state_after
            if before == after:
                continue
            self._states[change.subsystem] = after
            name = self._component_name(change.subsystem)
            cause = change.caused_by or self._attribute_cause(change.subsystem)
            direct = (
                cause is not None
                and self._active.get(cause) is not None
                and (self._active[cause].subsystem == change.subsystem)
            )
            metadata = {"reason": change.reason, "direct": direct}
            if after.is_healthy and not before.is_healthy:
                for event_id, request in list(self._active.items()):
                    if (
                        request.subsystem == change.subsystem
                        and request.effect in TRANSIENT_EFFECTS
                    ):
                        del self._active[event_id]
                opened = self._fault_open_since.pop(change.subsystem, None)
                recovery_time = None if opened is None else round(t - opened, 3)
                metadata["fault_duration"] = recovery_time
                await self._emit(
                    t=t,
                    kind=EventKind.RECOVERY,
                    event_type="recovered",
                    message=f"{name} {before.value} -> {after.value}"
                    + (f" (after {recovery_time:.1f}s)" if recovery_time else ""),
                    source=EventSource.ADAPTER,
                    severity=Severity.INFO,
                    subsystem=change.subsystem,
                    state_before=before,
                    state_after=after,
                    scenario_event_id=cause,
                    metadata=metadata,
                )
            elif not after.is_healthy:
                if before.is_healthy or before is ComponentState.UNKNOWN:
                    self._fault_open_since.setdefault(change.subsystem, t)
                severity = _SEVERITY_FOR_STATE.get(after, Severity.MEDIUM)
                if after is ComponentState.RECOVERING:
                    severity = Severity.INFO if not before.is_healthy else Severity.HIGH
                if change.subsystem in self.topology.critical_component_ids and after.is_down:
                    severity = Severity.CRITICAL
                await self._emit(
                    t=t,
                    kind=EventKind.OBSERVED_EFFECT,
                    event_type="state_change",
                    message=f"{name} {before.value} -> {after.value}"
                    + (f": {change.reason}" if change.reason else ""),
                    source=EventSource.ADAPTER,
                    severity=severity,
                    subsystem=change.subsystem,
                    state_before=before,
                    state_after=after,
                    scenario_event_id=cause,
                    metadata=metadata,
                )
            else:
                await self._emit(
                    t=t,
                    kind=EventKind.LOG,
                    event_type="state_normalized",
                    message=f"{name} {before.value} -> {after.value}",
                    source=EventSource.ADAPTER,
                    subsystem=change.subsystem,
                    state_before=before,
                    state_after=after,
                    metadata=metadata,
                )

        for response in observation.responses:
            await self._emit(
                t=t,
                kind=EventKind.SYSTEM_RESPONSE,
                event_type=response.response_type,
                message=response.message,
                source=EventSource.ADAPTER,
                severity=Severity.MEDIUM if response.safe_state else Severity.INFO,
                subsystem=response.subsystem,
                metadata={"safe_state": response.safe_state},
            )

        for mission_event in observation.mission_events:
            await self._emit(
                t=t,
                kind=EventKind.MISSION,
                event_type=mission_event.event_type,
                message=mission_event.message,
                source=EventSource.ADAPTER,
                metadata={"progress": mission_event.progress},
            )

        recovering = any(s is ComponentState.RECOVERING for s in self._states.values())
        if recovering and self._run_state is RunState.RUNNING:
            await self._set_run_state(RunState.RECOVERING, reason="component recovering", t=t)
        elif not recovering and self._run_state is RunState.RECOVERING:
            await self._set_run_state(RunState.RUNNING, reason="recovery complete", t=t)

    # ------------------------------------------------------------------ expectations

    def _expectation_status(self, pending: _PendingExpectation, t: float) -> bool | None:
        """Return True/False once the expectation is decided, None while pending.

        Semantics by expected state:

        - healthy (NOMINAL / OPERATIONAL): the component must stay healthy for the whole
          window; decided at the deadline, failed early if it leaves the healthy set;
        - RECOVERED: the component must leave the healthy set and return within the
          window; passed at the moment it returns;
        - any other state: passed the first time that exact state is observed.
        """

        expectation = pending.expectation
        observed = self._states.get(expectation.subsystem, ComponentState.UNKNOWN)
        expired = t > pending.deadline
        if expectation.state is ComponentState.RECOVERED:
            if not observed.is_healthy:
                pending.left_healthy = True
                return False if expired else None
            if pending.left_healthy:
                return True
            return False if expired else None
        if expectation.state.is_healthy:
            if not observed.is_healthy:
                return False
            return True if expired else None
        if observed == expectation.state:
            return True
        return False if expired else None

    async def _process_expectations(self, t: float) -> None:
        remaining: list[_PendingExpectation] = []
        for pending in self._expectations:
            if t <= pending.requested_at:
                remaining.append(pending)
                continue
            status = self._expectation_status(pending, t)
            if status is None:
                remaining.append(pending)
            else:
                await self._emit_expectation(pending, t, passed=status)
        self._expectations = remaining

    async def _flush_expectations_at_end(self, t: float) -> None:
        for pending in self._expectations:
            status = self._expectation_status(pending, t + max(pending.deadline, t) + 1.0)
            await self._emit_expectation(pending, t, passed=bool(status))
        self._expectations = []

    async def _emit_expectation(
        self, pending: _PendingExpectation, t: float, *, passed: bool
    ) -> None:
        expectation = pending.expectation
        observed = self._states.get(expectation.subsystem, ComponentState.UNKNOWN)
        name = self._component_name(expectation.subsystem)
        await self._emit(
            t=t,
            kind=EventKind.EXPECTATION_RESULT,
            event_type="expectation_passed" if passed else "expectation_failed",
            message=(
                f"Expected {name} {expectation.state.value} within {expectation.within}: "
                f"{'observed' if passed else 'not observed'} ({observed.value})"
            ),
            source=EventSource.ENGINE,
            severity=Severity.INFO if passed else Severity.HIGH,
            subsystem=expectation.subsystem,
            state_after=observed,
            scenario_event_id=pending.scenario_event_id,
            metadata={
                "expected_state": expectation.state.value,
                "within": expectation.within,
                "elapsed": round(t - pending.requested_at, 3),
                "passed": passed,
            },
        )

    # ------------------------------------------------------------------ telemetry

    async def _buffer_sample(self, sample: TelemetrySample) -> None:
        self._sample_count += 1
        if self._batch_started_at is None:
            self._batch_started_at = sample.t
        self._batch.append(sample)
        if (
            sample.t - self._batch_started_at >= self.telemetry_batch_seconds
            or len(self._batch) >= 200
        ):
            await self._flush_batch()

    async def _flush_batch(self, *, force: bool = False) -> None:
        if not self._batch:
            return
        batch, self._batch = self._batch, []
        self._batch_started_at = None
        await self.sink.on_telemetry(batch)


def scenario_duration_hint(scenario: ResilienceScenario) -> float:
    """Upper bound of the run duration in simulation seconds."""

    return parse_duration(scenario.mission.timeout)

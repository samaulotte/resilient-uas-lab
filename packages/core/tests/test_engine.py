from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from core_support import RUN_ID, healthy_states, make_sample

from reslab_core.adapter import (
    AdapterCapabilities,
    AdapterConfiguration,
    AdapterKind,
    ArtifactBlob,
    AutonomousSystemAdapter,
    ClearRequest,
    HealthReport,
    InjectionRequest,
    InjectionResult,
    Observation,
    Snapshot,
)
from reslab_core.engine import CancelToken, ScenarioEngine
from reslab_core.scenario import load_scenario
from reslab_core.scenario.catalog import Effect
from reslab_core.states import ComponentState, EventKind, FlightMode, MissionPhase, RunState
from reslab_core.telemetry import ComponentStateChange, PlannedPath, Position

SCENARIO = """
apiVersion: resilient-uas.dev/v1alpha1
kind: ResilienceScenario
metadata:
  name: engine-test
target:
  adapter: mock
mission:
  timeout: 60s
events:
  - id: gnss-loss
    at: 2s
    inject:
      subsystem: navigation.gnss
      effect: unavailable
      duration: 3s
    expect:
      - subsystem: navigation.gnss
        state: UNAVAILABLE
        within: 1s
  - id: restart
    at: 4s
    inject:
      subsystem: mission.compute
      effect: restart
assertions:
  - expression: flight_control.available == true
    severity: critical
"""


class ScriptedAdapter(AutonomousSystemAdapter):
    """Adapter that reacts to injections one step later and ends after `steps` samples."""

    def __init__(
        self, *, steps: int = 12, reject: set[str] | None = None, support_all: bool = True
    ):
        self.steps = steps
        self.reject = reject or set()
        self.support_all = support_all
        self.states = healthy_states()
        self.injected: list[InjectionRequest] = []
        self.cleared: list[ClearRequest] = []
        self.stopped = False
        self._pending_changes: list[ComponentStateChange] = []

    @property
    def capabilities(self) -> AdapterCapabilities:
        supported = {
            "navigation.gnss": (Effect.UNAVAILABLE,),
            "mission.compute": (Effect.RESTART,) if self.support_all else (),
        }
        return AdapterCapabilities(
            name="scripted",
            kind=AdapterKind.SIMULATION,
            description="test",
            vehicles=("x500",),
            supported_effects=supported,
            deterministic=True,
            data_origin="test",
        )

    async def prepare(self, configuration: AdapterConfiguration) -> PlannedPath:
        return PlannedPath(waypoints=[Position(x=0, y=0, z=10), Position(x=10, y=0, z=10)])

    async def start(self) -> None:
        pass

    async def inject(self, request: InjectionRequest) -> InjectionResult:
        self.injected.append(request)
        if request.scenario_event_id in self.reject:
            return InjectionResult(applied=False, mechanism="scripted", detail="rejected by test")
        state = (
            ComponentState.RECOVERING
            if request.effect is Effect.RESTART
            else ComponentState.UNAVAILABLE
        )
        self._pending_changes.append(
            ComponentStateChange(
                subsystem=request.subsystem,
                state_before=self.states[request.subsystem],
                state_after=state,
                reason="scripted",
            )
        )
        self.states[request.subsystem] = state
        return InjectionResult(applied=True, mechanism="scripted")

    async def clear(self, request: ClearRequest) -> InjectionResult:
        self.cleared.append(request)
        self._pending_changes.append(
            ComponentStateChange(
                subsystem=request.subsystem,
                state_before=self.states[request.subsystem],
                state_after=ComponentState.NOMINAL,
            )
        )
        self.states[request.subsystem] = ComponentState.NOMINAL
        return InjectionResult(applied=True, mechanism="scripted")

    async def observe(self) -> AsyncIterator[Observation]:
        for i in range(1, self.steps + 1):
            t = float(i)
            if self.states.get("mission.compute") is ComponentState.RECOVERING and t >= 7:
                self._pending_changes.append(
                    ComponentStateChange(
                        subsystem="mission.compute",
                        state_before=ComponentState.RECOVERING,
                        state_after=ComponentState.RECOVERED,
                    )
                )
                self.states["mission.compute"] = ComponentState.RECOVERED
            changes = tuple(self._pending_changes)
            self._pending_changes = []
            finished = i == self.steps
            yield Observation(
                sample=make_sample(
                    t,
                    health=dict(self.states),
                    phase=MissionPhase.COMPLETE if finished else MissionPhase.ENROUTE,
                    mode=FlightMode.LANDED if finished else FlightMode.MISSION,
                    progress=1.0 if finished else i / self.steps,
                ),
                state_changes=changes,
                finished=finished,
            )

    async def health(self) -> HealthReport:
        return HealthReport(t=0.0, states=dict(self.states))

    async def snapshot(self) -> Snapshot:
        return Snapshot(t=0.0, states=dict(self.states), active_effects=(), sample=None)

    async def stop(self) -> None:
        self.stopped = True

    async def collect_artifacts(self) -> list[ArtifactBlob]:
        return [ArtifactBlob(name="scripted.log", content_type="text/plain", data=b"ok")]


class RecordingSink:
    def __init__(self) -> None:
        self.lifecycle: list[RunState] = []
        self.events = []
        self.samples = []

    async def on_lifecycle(self, state, *, reason="", simulation_time=0.0, planned_path=None):
        self.lifecycle.append(state)

    async def on_event(self, event):
        self.events.append(event)

    async def on_telemetry(self, samples):
        self.samples.extend(samples)


async def test_engine_full_cycle() -> None:
    scenario = load_scenario(SCENARIO)
    adapter = ScriptedAdapter()
    sink = RecordingSink()
    engine = ScenarioEngine(run_id=RUN_ID, scenario=scenario, adapter=adapter, sink=sink)
    result = await engine.run()

    assert result.final_state is RunState.COLLECTING
    assert result.mission_complete
    assert adapter.stopped
    assert [a.name for a in result.artifacts] == ["scripted.log"]
    assert sink.lifecycle[:2] == [RunState.PREPARING, RunState.RUNNING]
    assert RunState.RECOVERING in sink.lifecycle
    assert sink.lifecycle[-1] is RunState.COLLECTING
    assert len(sink.samples) == 12

    kinds = [e.kind for e in sink.events]
    assert kinds.count(EventKind.INJECTION_REQUEST) == 2
    assert kinds.count(EventKind.INJECTION_APPLIED) == 2
    assert EventKind.INJECTION_CLEARED in kinds  # gnss bounded duration
    assert EventKind.OBSERVED_EFFECT in kinds
    assert EventKind.RECOVERY in kinds
    expectation = next(e for e in sink.events if e.kind is EventKind.EXPECTATION_RESULT)
    assert expectation.metadata["passed"] is True
    # the clear happened at 2s + 3s
    cleared = next(e for e in sink.events if e.kind is EventKind.INJECTION_CLEARED)
    assert cleared.simulation_time == 5.0
    assert [c.subsystem for c in adapter.cleared] == ["navigation.gnss"]
    # sequence numbers are strictly increasing
    assert [e.sequence for e in sink.events] == list(range(len(sink.events)))


async def test_engine_records_rejected_injection() -> None:
    scenario = load_scenario(SCENARIO)
    adapter = ScriptedAdapter(reject={"gnss-loss"})
    sink = RecordingSink()
    result = await ScenarioEngine(
        run_id=RUN_ID, scenario=scenario, adapter=adapter, sink=sink
    ).run()
    assert result.final_state is RunState.COLLECTING
    rejected = [e for e in sink.events if e.kind is EventKind.INJECTION_REJECTED]
    assert len(rejected) == 1 and rejected[0].scenario_event_id == "gnss-loss"
    # no expectation is evaluated for an injection that never happened
    assert not [e for e in sink.events if e.kind is EventKind.EXPECTATION_RESULT]


async def test_engine_fails_fast_on_unsupported_effect() -> None:
    scenario = load_scenario(SCENARIO)
    adapter = ScriptedAdapter(support_all=False)
    sink = RecordingSink()
    result = await ScenarioEngine(
        run_id=RUN_ID, scenario=scenario, adapter=adapter, sink=sink
    ).run()
    assert result.final_state is RunState.FAILED
    assert "mission.compute:restart" in result.reason
    assert not adapter.injected
    assert sink.events[0].kind is EventKind.INJECTION_REJECTED


async def test_engine_cancellation() -> None:
    scenario = load_scenario(SCENARIO)
    adapter = ScriptedAdapter(steps=50)
    sink = RecordingSink()
    token = CancelToken()

    async def cancel_after_three(_samples):
        if len(sink.samples) >= 3:
            token.cancel("user request")

    original = sink.on_telemetry

    async def on_telemetry(samples):
        await original(samples)
        await cancel_after_three(samples)

    sink.on_telemetry = on_telemetry  # type: ignore[method-assign]
    engine = ScenarioEngine(
        run_id=RUN_ID,
        scenario=scenario,
        adapter=adapter,
        sink=sink,
        cancel_token=token,
        telemetry_batch_seconds=0.0,
    )
    result = await engine.run()
    assert result.final_state is RunState.CANCELLED
    assert result.reason == "user request"
    assert any(e.event_type == "run_cancelled" for e in sink.events)
    assert adapter.stopped


async def test_engine_handles_adapter_exception() -> None:
    class Broken(ScriptedAdapter):
        async def start(self) -> None:
            raise RuntimeError("simulator unreachable")

    scenario = load_scenario(SCENARIO)
    sink = RecordingSink()
    result = await ScenarioEngine(
        run_id=RUN_ID, scenario=scenario, adapter=Broken(), sink=sink
    ).run()
    assert result.final_state is RunState.FAILED
    assert "simulator unreachable" in result.reason
    assert any(e.event_type == "target_failure" for e in sink.events)


@pytest.mark.parametrize("speed", [1.0, 10.0])
def test_engine_speed_defaults_from_scenario(speed: float) -> None:
    scenario = load_scenario(
        SCENARIO.replace("mission:\n", f"simulation:\n  speed: {speed}\nmission:\n")
    )
    engine = ScenarioEngine(
        run_id=RUN_ID, scenario=scenario, adapter=ScriptedAdapter(), sink=RecordingSink()
    )
    assert engine.speed == speed

from __future__ import annotations

from pathlib import Path

import pytest

from reslab_adapter_mock import MOCK_CAPABILITIES, MockAdapter
from reslab_core.adapter import AdapterConfiguration, ClearRequest, InjectionRequest
from reslab_core.analysis.metrics import compute_metrics
from reslab_core.engine import ScenarioEngine
from reslab_core.scenario import load_scenario, load_scenario_file
from reslab_core.scenario.catalog import DEFAULT_CATALOG, Effect
from reslab_core.scenario.model import Mission, RecoveryPolicy, SimulationConfig, Target
from reslab_core.states import ComponentState, EventKind, FlightMode, MissionPhase, RunState
from reslab_core.topology import DEFAULT_TOPOLOGY

SCENARIOS = Path(__file__).resolve().parents[3] / "scenarios"
RUN_ID = "00000000-0000-4000-8000-000000000002"


class Sink:
    def __init__(self) -> None:
        self.events = []
        self.samples = []
        self.lifecycle = []

    async def on_lifecycle(self, state, *, reason="", simulation_time=0.0, planned_path=None):
        self.lifecycle.append(state)

    async def on_event(self, event):
        self.events.append(event)

    async def on_telemetry(self, samples):
        self.samples.extend(samples)


async def run_scenario(path_or_text: str | Path, *, seed: int | None = None):
    scenario = (
        load_scenario_file(path_or_text)
        if isinstance(path_or_text, Path)
        else load_scenario(path_or_text)
    )
    sink = Sink()
    engine = ScenarioEngine(
        run_id=RUN_ID, scenario=scenario, adapter=MockAdapter(), sink=sink, speed=100.0, seed=seed
    )
    result = await engine.run()
    return scenario, result, sink


def _config(seed: int = 1) -> AdapterConfiguration:
    return AdapterConfiguration(
        run_id=RUN_ID,
        target=Target(adapter="mock"),
        mission=Mission(timeout="120s"),
        recovery=RecoveryPolicy(),
        simulation=SimulationConfig(seed=seed, speed=100.0),
        topology=DEFAULT_TOPOLOGY,
    )


def test_capabilities_cover_catalog() -> None:
    for entry in DEFAULT_CATALOG.entries:
        for effect in entry.effects:
            assert MOCK_CAPABILITIES.supports(entry.component.id, effect)
    assert MOCK_CAPABILITIES.deterministic
    assert (
        "hardware" not in MOCK_CAPABILITIES.data_origin
        or "no hardware" in MOCK_CAPABILITIES.data_origin
    )


async def test_adapter_contract_lifecycle() -> None:
    adapter = MockAdapter()
    planned = await adapter.prepare(_config())
    assert len(planned.waypoints) >= 2
    await adapter.start()
    health = await adapter.health()
    assert set(health.states) == set(DEFAULT_TOPOLOGY.component_ids)
    result = await adapter.inject(
        InjectionRequest(
            scenario_event_id="e1", subsystem="navigation.gnss", effect=Effect.UNAVAILABLE
        )
    )
    assert result.applied
    snapshot = await adapter.snapshot()
    assert [e.scenario_event_id for e in snapshot.active_effects] == ["e1"]
    rejected = await adapter.inject(
        InjectionRequest(scenario_event_id="e2", subsystem="nope.nope", effect=Effect.UNAVAILABLE)
    )
    assert not rejected.applied
    cleared = await adapter.clear(
        ClearRequest(scenario_event_id="e1", subsystem="navigation.gnss", effect=Effect.UNAVAILABLE)
    )
    assert cleared.applied
    count = 0
    async for _observation in adapter.observe():
        count += 1
        if count >= 5:
            await adapter.stop()
    assert count >= 5
    artifacts = await adapter.collect_artifacts()
    assert {a.name for a in artifacts} == {"mock-adapter.log", "mock-injections.json"}


async def test_determinism_same_seed_identical_telemetry() -> None:
    _, _, a = await run_scenario(SCENARIOS / "compound-degradation.yaml", seed=42)
    _, _, b = await run_scenario(SCENARIOS / "compound-degradation.yaml", seed=42)
    assert len(a.samples) == len(b.samples)
    for sa, sb in zip(a.samples, b.samples, strict=True):
        assert sa.model_dump(exclude={"wall_time"}) == sb.model_dump(exclude={"wall_time"})
    assert [(e.kind, e.subsystem, e.simulation_time) for e in a.events] == [
        (e.kind, e.subsystem, e.simulation_time) for e in b.events
    ]


async def test_different_seed_changes_trajectory() -> None:
    _, _, a = await run_scenario(SCENARIOS / "compound-degradation.yaml", seed=1)
    _, _, b = await run_scenario(SCENARIOS / "compound-degradation.yaml", seed=2)
    positions_a = [(s.position.x, s.position.y) for s in a.samples[200:400]]
    positions_b = [(s.position.x, s.position.y) for s in b.samples[200:400]]
    assert positions_a != positions_b


async def test_compound_scenario_expected_sequence() -> None:
    _, result, sink = await run_scenario(SCENARIOS / "compound-degradation.yaml")
    assert result.final_state is RunState.COLLECTING
    assert result.mission_complete
    assert RunState.RECOVERING in sink.lifecycle

    def first(kind: EventKind, subsystem: str, after: ComponentState | None = None):
        for e in sink.events:
            if (
                e.kind is kind
                and e.subsystem == subsystem
                and (after is None or e.state_after is after)
            ):
                return e
        raise AssertionError(f"no {kind} for {subsystem}")

    gnss = first(EventKind.OBSERVED_EFFECT, "navigation.gnss", ComponentState.UNAVAILABLE)
    assert 30.0 <= gnss.simulation_time <= 30.5
    estimator = first(EventKind.OBSERVED_EFFECT, "navigation.estimator", ComponentState.DEGRADED)
    assert estimator.simulation_time - gnss.simulation_time <= 1.0
    c2 = first(EventKind.OBSERVED_EFFECT, "communications.c2", ComponentState.UNAVAILABLE)
    assert 45.0 <= c2.simulation_time <= 45.5
    autonomy = next(e for e in sink.events if e.event_type == "local_autonomy_active")
    assert autonomy.simulation_time - c2.simulation_time <= 0.5
    restart = first(EventKind.OBSERVED_EFFECT, "mission.compute", ComponentState.RECOVERING)
    assert 60.0 <= restart.simulation_time <= 60.5
    recovered = first(EventKind.RECOVERY, "mission.compute")
    assert 3.0 <= recovered.simulation_time - restart.simulation_time <= 6.0
    hold = next(e for e in sink.events if e.event_type == "failsafe_hold")
    assert hold.metadata["safe_state"] is True

    # flight control never leaves an operational state
    assert all(s.health["flight_control.core"] is ComponentState.OPERATIONAL for s in sink.samples)
    assert all(s.flight.control_authority for s in sink.samples)
    # mission completes and lands
    assert sink.samples[-1].mission.phase is MissionPhase.COMPLETE
    assert sink.samples[-1].flight.mode is FlightMode.LANDED

    metrics = compute_metrics(events=sink.events, samples=sink.samples)
    assert metrics.propagation.contained
    assert metrics.recovery.faults_recovered >= 1
    assert metrics.mission.completion == 1.0
    assert metrics.events.injected == 3 and metrics.events.applied == 3


@pytest.mark.parametrize(
    "name",
    [
        "gnss-loss",
        "datalink-loss",
        "sensor-failure",
        "mission-compute-restart",
        "resource-pressure",
        "em-transient-profile-a",
    ],
)
async def test_all_starter_scenarios_complete_with_contained_faults(name: str) -> None:
    _, result, sink = await run_scenario(SCENARIOS / f"{name}.yaml")
    assert result.final_state is RunState.COLLECTING, result.reason
    assert result.mission_complete
    metrics = compute_metrics(events=sink.events, samples=sink.samples)
    assert metrics.propagation.contained
    assert metrics.safety.preserved
    assert not [e for e in sink.events if e.kind is EventKind.INJECTION_REJECTED]


def _scenario(events_yaml: str, recovery: str = "") -> str:
    return f"""
apiVersion: resilient-uas.dev/v1alpha1
kind: ResilienceScenario
metadata:
  name: effect-test
target:
  adapter: mock
mission:
  timeout: 150s
{recovery}
events:
{events_yaml}
"""


async def test_datalink_hold_policy_enters_hold() -> None:
    text = _scenario(
        """
  - id: c2
    at: 20s
    inject:
      subsystem: communications.c2
      effect: unavailable
      duration: 10s
""",
        recovery="recovery:\n  datalink_loss: hold\n",
    )
    _, _, sink = await run_scenario(text)
    holds = [e for e in sink.events if e.event_type == "failsafe_hold"]
    assert holds and 20.0 <= holds[0].simulation_time <= 20.5
    resumed = [e for e in sink.events if e.event_type == "mission_resumed"]
    assert resumed and 30.0 <= resumed[0].simulation_time <= 31.0


async def test_security_gateway_fails_closed() -> None:
    text = _scenario(
        """
  - id: gw
    at: 20s
    inject:
      subsystem: security.gateway
      effect: unavailable
      duration: 5s
"""
    )
    _, _, sink = await run_scenario(text)
    hold = next(e for e in sink.events if e.event_type == "failsafe_hold")
    assert "fail-closed" in hold.message
    assert all(s.health["flight_control.core"] is ComponentState.OPERATIONAL for s in sink.samples)


async def test_flight_core_degradation_is_flagged_as_propagation() -> None:
    text = _scenario(
        """
  - id: imu
    at: 20s
    inject:
      subsystem: sensors.imu
      effect: erroneous
      duration: 10s
"""
    )
    _, _, sink = await run_scenario(text)
    metrics = compute_metrics(events=sink.events, samples=sink.samples)
    assert metrics.propagation.flight_domain_affected
    assert not metrics.propagation.contained
    assert not metrics.safety.flight_control_available
    assert not metrics.safety.loss_of_control  # degraded, but still controlled


async def test_power_bus_transient_causes_companion_brownout() -> None:
    text = _scenario(
        """
  - id: bus
    at: 20s
    inject:
      subsystem: power.bus
      effect: degraded
      duration: 3s
      parameters:
        level: 0.3
"""
    )
    _, _, sink = await run_scenario(text)
    compute_down = [
        e
        for e in sink.events
        if e.kind is EventKind.OBSERVED_EFFECT and e.subsystem == "mission.compute"
    ]
    assert compute_down and compute_down[0].state_after is ComponentState.RECOVERING
    metrics = compute_metrics(events=sink.events, samples=sink.samples)
    assert "mission.compute" in metrics.propagation.propagated_components
    assert metrics.propagation.contained


async def test_crash_recovers_after_watchdog_and_restart() -> None:
    text = _scenario(
        """
  - id: crash
    at: 20s
    inject:
      subsystem: mission.planner
      effect: crash
"""
    )
    _, _, sink = await run_scenario(text)
    failed = next(
        e
        for e in sink.events
        if e.kind is EventKind.OBSERVED_EFFECT
        and e.subsystem == "mission.planner"
        and e.state_after is ComponentState.FAILED
    )
    recovered = next(
        e for e in sink.events if e.kind is EventKind.RECOVERY and e.subsystem == "mission.planner"
    )
    assert 4.0 <= recovered.simulation_time - failed.simulation_time <= 9.0

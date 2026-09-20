from __future__ import annotations

import json

import pytest
from core_support import RUN_ID, healthy_states, make_event, make_sample

from reslab_core.analysis.assertions import evaluate_assertions
from reslab_core.analysis.metrics import compute_metrics
from reslab_core.analysis.scoring import (
    DEFAULT_SCORE_PROFILE,
    ScoreProfile,
    compute_score,
)
from reslab_core.provenance import Provenance
from reslab_core.report import build_report, render_html_report
from reslab_core.scenario import load_scenario
from reslab_core.states import (
    BenchmarkResult,
    ComponentState,
    EventKind,
    EventSource,
    FlightMode,
    MissionPhase,
    RunState,
)
from reslab_core.topology import DEFAULT_TOPOLOGY, Domain

SCENARIO = """
apiVersion: resilient-uas.dev/v1alpha1
kind: ResilienceScenario
metadata:
  name: synthetic
target:
  adapter: mock
mission:
  timeout: 120s
events:
  - id: restart
    at: 10s
    inject:
      subsystem: mission.compute
      effect: restart
assertions:
  - expression: flight_control.available == true
    severity: critical
  - expression: recovery.mission_compute < 6s
    severity: high
  - expression: mission.completion >= 0.9
    severity: medium
"""


def _synthetic_run(*, fc_fails: bool = False):
    """A 100 s run: compute restarts at t=10, recovers at t=15, mission completes."""

    deg, rec, recd, op, unav = (
        ComponentState.DEGRADED,
        ComponentState.RECOVERING,
        ComponentState.RECOVERED,
        ComponentState.OPERATIONAL,
        ComponentState.UNAVAILABLE,
    )
    samples = []
    for i in range(0, 101):
        t = float(i)
        health = healthy_states()
        mode = FlightMode.MISSION
        if 10 <= t < 15:
            health["mission.compute"] = rec
            health["mission.planner"] = unav
            mode = FlightMode.HOLD
        elif 15 <= t < 16:
            health["mission.compute"] = recd
        if fc_fails and 20 <= t < 25:
            health["flight_control.core"] = deg
        phase = MissionPhase.COMPLETE if t >= 100 else MissionPhase.ENROUTE
        samples.append(
            make_sample(t, health=health, mode=mode, phase=phase, progress=min(1.0, t / 100), x=t)
        )
    events = [
        make_event(
            0,
            10.0,
            EventKind.INJECTION_REQUEST,
            subsystem="mission.compute",
            scenario_event_id="restart",
            metadata={"effect": "restart"},
            event_type="injection_requested",
            source=EventSource.SCENARIO,
        ),
        make_event(
            1,
            10.0,
            EventKind.INJECTION_APPLIED,
            subsystem="mission.compute",
            scenario_event_id="restart",
            metadata={"mechanism": "test"},
            event_type="injection_applied",
        ),
        make_event(
            2,
            10.0,
            EventKind.OBSERVED_EFFECT,
            subsystem="mission.compute",
            before=op,
            after=rec,
            scenario_event_id="restart",
            metadata={"direct": True},
        ),
        make_event(
            3,
            10.0,
            EventKind.OBSERVED_EFFECT,
            subsystem="mission.planner",
            before=op,
            after=unav,
            scenario_event_id="restart",
            metadata={"direct": False},
        ),
        make_event(
            4,
            10.0,
            EventKind.SYSTEM_RESPONSE,
            subsystem="flight_control.core",
            event_type="failsafe_hold",
            metadata={"safe_state": True},
        ),
        make_event(
            5,
            15.0,
            EventKind.RECOVERY,
            subsystem="mission.compute",
            before=rec,
            after=recd,
            scenario_event_id="restart",
            event_type="recovered",
        ),
        make_event(
            6,
            15.0,
            EventKind.RECOVERY,
            subsystem="mission.planner",
            before=unav,
            after=op,
            scenario_event_id="restart",
            event_type="recovered",
        ),
    ]
    if fc_fails:
        events.append(
            make_event(
                7,
                20.0,
                EventKind.OBSERVED_EFFECT,
                subsystem="flight_control.core",
                before=op,
                after=deg,
                metadata={"direct": False},
            )
        )
    return events, samples


def test_metrics_from_synthetic_run() -> None:
    events, samples = _synthetic_run()
    metrics = compute_metrics(events=events, samples=samples)
    assert metrics.run_duration == 100.0
    assert metrics.mission.completed
    assert metrics.mission.completion == 1.0
    assert metrics.mission.continuity == pytest.approx(0.95)
    assert metrics.availability.control == pytest.approx(1.0)
    assert metrics.availability.compute == pytest.approx(0.95)
    assert metrics.recovery.mean_time_to_recovery == pytest.approx(5.0)
    assert metrics.recovery.faults_requiring_recovery == 2
    assert metrics.recovery.success_rate == 1.0
    assert metrics.recovery.time_to_safe_state == 0.0
    assert metrics.propagation.injected_components == ["mission.compute"]
    assert metrics.propagation.propagated_components == ["mission.planner"]
    assert metrics.propagation.max_propagation_depth == 1
    assert metrics.propagation.affected_domains == [Domain.MISSION_COMPUTE]
    assert metrics.propagation.contained
    assert not metrics.propagation.flight_domain_affected
    assert metrics.modes.time_degraded == pytest.approx(5.0)
    assert metrics.modes.time_nominal == pytest.approx(95.0)
    assert metrics.safety.preserved
    ctx = metrics.assertion_context()
    assert ctx["recovery.mission_compute"] == 5.0
    assert ctx["containment.flight_domain_affected"] is False


def test_metrics_detect_flight_domain_propagation() -> None:
    events, samples = _synthetic_run(fc_fails=True)
    metrics = compute_metrics(events=events, samples=samples)
    assert metrics.propagation.flight_domain_affected
    assert not metrics.propagation.contained
    assert not metrics.safety.flight_control_available
    assert metrics.availability.control == pytest.approx(0.95)
    assert Domain.FLIGHT_CONTROL in metrics.propagation.affected_domains


def test_score_profile_weights_must_sum_to_100() -> None:
    with pytest.raises(ValueError):
        ScoreProfile(name="bad", weights={"safety": 50, "recovery": 40})
    with pytest.raises(ValueError):
        ScoreProfile(name="bad", weights={"safety": 100, "unknown": 0})
    assert sum(DEFAULT_SCORE_PROFILE.weights.values()) == 100


def test_score_and_hard_gates() -> None:
    scenario = load_scenario(SCENARIO)
    events, samples = _synthetic_run()
    metrics = compute_metrics(events=events, samples=samples)
    assertions = evaluate_assertions(scenario.assertions, metrics.assertion_context())
    score = compute_score(metrics, assertions)
    assert score.result is BenchmarkResult.PASSED
    assert 85 < score.total <= 100
    assert sum(d.weight for d in score.dimensions) == 100
    assert all(0 <= d.score <= 1 for d in score.dimensions)


def test_critical_assertion_overrides_score() -> None:
    scenario = load_scenario(SCENARIO)
    events, samples = _synthetic_run(fc_fails=True)
    metrics = compute_metrics(events=events, samples=samples)
    assertions = evaluate_assertions(scenario.assertions, metrics.assertion_context())
    score = compute_score(metrics, assertions)
    assert score.result is BenchmarkResult.FAILED
    assert score.hard_gate_result is BenchmarkResult.FAILED
    assert "critical assertion violated" in score.reason
    assert score.total > 50  # the number stays visible, the verdict is failed


def test_incomplete_run_is_inconclusive() -> None:
    events, samples = _synthetic_run()
    metrics = compute_metrics(events=events, samples=samples)
    score = compute_score(metrics, [], run_completed=False)
    assert score.result is BenchmarkResult.INCONCLUSIVE


def test_unevaluable_critical_assertion_is_inconclusive() -> None:
    # A critical assertion whose metric was never observed makes the whole benchmark
    # inconclusive, not passed: we cannot claim a safety property we could not measure.
    from reslab_core.analysis.assertions import evaluate_assertion
    from reslab_core.scenario.model import Assertion
    from reslab_core.states import AssertionOutcome, Severity

    events, samples = _synthetic_run()
    metrics = compute_metrics(events=events, samples=samples)
    # The navigation estimator never faulted in this run, so its recovery time was never
    # observed: a critical assertion on it cannot be evaluated.
    unmeasured = evaluate_assertion(
        Assertion(expression="recovery.navigation_estimator < 10s", severity=Severity.CRITICAL),
        metrics.assertion_context(),
    )
    assert unmeasured.outcome is AssertionOutcome.NOT_EVALUATED
    score = compute_score(metrics, [unmeasured])
    assert score.result is BenchmarkResult.INCONCLUSIVE
    assert "could not be evaluated" in score.reason


def test_positive_failure_beats_unevaluable_assertion() -> None:
    # When one critical assertion fails outright and another cannot be evaluated, the run
    # has failed: positive evidence of failure wins over an observability gap.
    from reslab_core.analysis.assertions import evaluate_assertion
    from reslab_core.scenario.model import Assertion
    from reslab_core.states import Severity

    events, samples = _synthetic_run(fc_fails=True)
    metrics = compute_metrics(events=events, samples=samples)
    failed = evaluate_assertion(
        Assertion(expression="flight_control.available == true", severity=Severity.CRITICAL),
        metrics.assertion_context(),
    )
    unmeasured = evaluate_assertion(
        Assertion(expression="recovery.mission_compute < 10s", severity=Severity.CRITICAL),
        metrics.assertion_context(),
    )
    score = compute_score(metrics, [failed, unmeasured])
    assert score.result is BenchmarkResult.FAILED


def test_report_build_and_render(tmp_path) -> None:
    scenario = load_scenario(SCENARIO)
    events, samples = _synthetic_run()
    provenance = Provenance(
        scenario_hash="sha256:abc", scenario_version="1", adapter="mock", seed=1, speed=1.0
    )
    report = build_report(
        run_id=RUN_ID,
        scenario=scenario,
        scenario_hash="sha256:abc",
        events=events,
        samples=samples,
        provenance=provenance,
        run_state=RunState.COMPLETED,
        started_at=None,
        ended_at=None,
    )
    assert report.schema_version == "1.0"
    assert report.result is BenchmarkResult.PASSED
    assert report.summary.faults_injected == 1
    assert report.summary.recovered_subsystems == 2
    assert report.summary.safety_preservation == "PASS"
    assert report.summary.fault_containment == "PASS"
    assert report.topology.id == DEFAULT_TOPOLOGY.id
    assert any(i.state is ComponentState.RECOVERING for i in report.subsystem_timeline)

    data = json.loads(report.model_dump_json())
    assert data["schema_version"] == "1.0"
    assert data["metrics"]["recovery"]["mean_time_to_recovery"] == 5.0

    html = render_html_report(report)
    assert "<!doctype html>" in html.lower()
    assert "synthetic" in html
    assert "Fault propagation" in html
    assert "<script" not in html.lower()
    (tmp_path / "report.html").write_text(html)

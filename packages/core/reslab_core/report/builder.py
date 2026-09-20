"""Assemble a `ResilienceReport` from persisted run data."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from reslab_core.analysis.assertions import evaluate_assertions
from reslab_core.analysis.metrics import compute_metrics
from reslab_core.analysis.scoring import DEFAULT_SCORE_PROFILE, ScoreProfile, compute_score
from reslab_core.provenance import Provenance
from reslab_core.report.model import (
    ComponentStateInterval,
    PathPoint,
    ReportArtifact,
    ReportRun,
    ReportScenario,
    ReportSummary,
    ReportTarget,
    ResilienceReport,
    downsample_positions,
    position_point,
)
from reslab_core.scenario.loader import scenario_to_yaml
from reslab_core.scenario.model import ResilienceScenario
from reslab_core.states import ComponentState, EventKind, RunState, Severity
from reslab_core.telemetry import PlannedPath, RunEvent, TelemetrySample, utcnow
from reslab_core.topology import DEFAULT_TOPOLOGY, SystemTopology


def subsystem_timeline(samples: Sequence[TelemetrySample]) -> list[ComponentStateInterval]:
    """Compress per-sample health maps into contiguous state intervals."""

    intervals: list[ComponentStateInterval] = []
    open_intervals: dict[str, tuple[ComponentState, float]] = {}
    last_t = 0.0
    for sample in sorted(samples, key=lambda s: s.t):
        last_t = sample.t
        for subsystem, state in sample.health.items():
            current = open_intervals.get(subsystem)
            if current is None:
                open_intervals[subsystem] = (state, sample.t)
            elif current[0] != state:
                intervals.append(
                    ComponentStateInterval(
                        subsystem=subsystem, state=current[0], start=current[1], end=sample.t
                    )
                )
                open_intervals[subsystem] = (state, sample.t)
    for subsystem, (state, start) in open_intervals.items():
        intervals.append(
            ComponentStateInterval(subsystem=subsystem, state=state, start=start, end=last_t)
        )
    intervals.sort(key=lambda i: (i.subsystem, i.start))
    return intervals


def build_report(
    *,
    run_id: str,
    scenario: ResilienceScenario,
    scenario_hash: str,
    events: Sequence[RunEvent],
    samples: Sequence[TelemetrySample],
    provenance: Provenance,
    run_state: RunState,
    started_at: datetime | None,
    ended_at: datetime | None,
    reason: str = "",
    planned_path: PlannedPath | None = None,
    artifacts: Sequence[ReportArtifact] = (),
    score_profile: ScoreProfile = DEFAULT_SCORE_PROFILE,
    topology: SystemTopology = DEFAULT_TOPOLOGY,
    adapter_version: str | None = None,
) -> ResilienceReport:
    metrics = compute_metrics(events=events, samples=samples, topology=topology)
    simulation_time = samples[-1].t if samples else metrics.run_duration
    assertions = evaluate_assertions(
        scenario.assertions, metrics.assertion_context(), simulation_time=simulation_time
    )
    run_completed = run_state is RunState.COMPLETED or run_state is RunState.ANALYZING
    score = compute_score(metrics, assertions, score_profile, run_completed=run_completed)

    critical_failures = sum(
        1 for e in events if e.kind is EventKind.OBSERVED_EFFECT and e.severity is Severity.CRITICAL
    )
    recovered_subsystems = len(
        {e.subsystem for e in events if e.kind is EventKind.RECOVERY and e.subsystem}
    )
    summary = ReportSummary(
        mission_complete=metrics.mission.completed,
        faults_injected=metrics.events.injected,
        faults_applied=metrics.events.applied,
        critical_failures=critical_failures,
        recovered_subsystems=recovered_subsystems,
        degraded_transitions=metrics.events.degraded_transitions,
        loss_of_control=metrics.safety.loss_of_control,
        safety_preservation="PASS" if metrics.safety.preserved else "FAIL",
        fault_containment="PASS" if metrics.propagation.contained else "FAIL",
        mean_time_to_recovery=metrics.recovery.mean_time_to_recovery,
        affected_domains=len(metrics.propagation.affected_domains),
    )

    actual_path = downsample_positions(
        [position_point(s.t, s.position) for s in sorted(samples, key=lambda s: s.t)]
    )

    return ResilienceReport(
        run_id=run_id,
        generated_at=utcnow(),
        scenario=ReportScenario(
            name=scenario.metadata.name,
            description=scenario.metadata.description,
            version=scenario.metadata.version,
            api_version=scenario.api_version,
            content_hash=scenario_hash,
            document=scenario_to_yaml(scenario),
            event_count=len(scenario.expanded_events()),
            assertion_count=len(scenario.assertions),
            mission_timeout=scenario.mission.timeout,
        ),
        target=ReportTarget(
            adapter=scenario.target.adapter,
            adapter_version=adapter_version or provenance.adapter_version,
            vehicle=scenario.target.vehicle,
            configuration=dict(scenario.target.configuration),
            data_origin=provenance.data_origin,
            topology_id=topology.id,
        ),
        run=ReportRun(
            state=run_state,
            started_at=started_at,
            ended_at=ended_at,
            simulation_duration=round(simulation_time, 3),
            seed=provenance.seed,
            speed=provenance.speed,
            reason=reason,
        ),
        result=score.result,
        resilience_score=score.total,
        hard_gate_result=score.hard_gate_result,
        summary=summary,
        score=score,
        metrics=metrics,
        assertions=assertions,
        events=list(sorted(events, key=lambda e: e.sequence)),
        subsystem_timeline=subsystem_timeline(samples),
        planned_path=planned_path,
        actual_path=actual_path,
        topology=topology,
        artifacts=list(artifacts),
        provenance=provenance,
    )


def path_points_from_samples(samples: Sequence[TelemetrySample]) -> list[PathPoint]:
    return [position_point(s.t, s.position) for s in samples]

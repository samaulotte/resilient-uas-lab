"""Resilience metrics engine.

Every metric is computed from observed data (run events and telemetry samples), never
from what the scenario requested. Definitions are documented in `docs/metrics.md`
and mirrored in the docstrings below.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field

from reslab_core.states import (
    ComponentState,
    EventKind,
    FlightMode,
    MissionPhase,
    SystemMode,
    aggregate_system_mode,
)
from reslab_core.telemetry import RunEvent, TelemetrySample
from reslab_core.topology import CRITICAL_DOMAINS, DEFAULT_TOPOLOGY, Domain, SystemTopology


class RecoveryRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    subsystem: str
    fault_state: ComponentState
    fault_started_at: float
    recovered_at: float | None
    fault_duration: float | None = Field(description="Seconds from fault start to recovery")
    recovery_time: float | None = Field(
        description=(
            "Seconds needed to recover once the disturbance ended: measured from the "
            "moment the causing injection was cleared (or from fault start for transient "
            "and self-inflicted faults) to the return to a healthy state"
        )
    )
    disturbance_cleared_at: float | None = Field(
        default=None, description="When the causing injection was cleared, if bounded"
    )
    caused_by: str | None = Field(description="Scenario event id when attributable")
    direct: bool = Field(description="True when the fault is the injected subsystem itself")
    recovery_expected: bool = Field(
        description="False when the injected effect persisted until scenario end"
    )


class MissionMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    completion: float = Field(ge=0, le=1, description="Fraction of mission objectives reached")
    continuity: float = Field(ge=0, le=1, description="1 - (time held or diverted / duration)")
    completed: bool
    duration: float = Field(description="Simulation seconds from start to end of run")
    time_in_hold: float
    time_in_mission_modes: float


class AvailabilityMetrics(BaseModel):
    """Fraction of run time during which a domain delivered its function."""

    model_config = ConfigDict(frozen=True)

    control: float = Field(ge=0, le=1)
    navigation_integrity: float = Field(
        ge=0, le=1, description="Weighted: healthy 1.0, degraded 0.5, down 0.0"
    )
    navigation: float = Field(ge=0, le=1)
    communications: float = Field(ge=0, le=1)
    compute: float = Field(ge=0, le=1)
    power: float = Field(ge=0, le=1)


class RecoveryMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    records: list[RecoveryRecord]
    mean_time_to_recovery: float | None = Field(description="Seconds; None when nothing recovered")
    max_time_to_recovery: float | None
    faults_requiring_recovery: int
    faults_recovered: int
    success_rate: float | None = Field(description="recovered / requiring; None when none required")
    time_to_safe_state: float | None = Field(
        description=(
            "Seconds from the observed fault that triggered the first safe-state response "
            "to that response"
        )
    )
    safe_state_entered: bool
    per_subsystem_max: dict[str, float] = Field(
        description="Maximum recovery time per subsystem (seconds)"
    )


class PropagationMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    injected_components: list[str]
    affected_components: list[str]
    propagated_components: list[str] = Field(
        description="Affected components that were not injection targets"
    )
    affected_domains: list[Domain]
    injected_domains: list[Domain]
    propagated_domains: list[Domain]
    propagation_count: int
    max_propagation_depth: int
    depths: dict[str, int]
    critical_domain_reached: bool
    flight_domain_affected: bool
    contained: bool
    boundary_crossed: bool = Field(description="A trust boundary was crossed by the propagation")


class ModeMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    time_nominal: float
    time_degraded: float
    time_failed: float
    total: float


class SafetyMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    loss_of_control: bool
    control_availability: float
    flight_control_available: bool = Field(description="Flight core never left a healthy state")
    preserved: bool = Field(description="No loss of control and flight core always available")
    safe_state_reached: bool


class EventCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    injected: int
    applied: int
    rejected: int
    cleared: int
    observed_effects: int
    system_responses: int
    recoveries: int
    expectations_passed: int
    expectations_failed: int
    degraded_transitions: int
    failed_transitions: int


class MetricsResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_duration: float
    sample_count: int
    mission: MissionMetrics
    availability: AvailabilityMetrics
    recovery: RecoveryMetrics
    propagation: PropagationMetrics
    modes: ModeMetrics
    safety: SafetyMetrics
    events: EventCounts
    component_time_in_state: dict[str, dict[str, float]]
    final_component_states: dict[str, ComponentState]

    def assertion_context(self) -> dict[str, float | bool | int | None]:
        """Flat namespace consumed by assertion expressions (see docs/metrics.md)."""

        ctx: dict[str, float | bool | int | None] = {
            "flight_control.available": self.safety.flight_control_available,
            "flight_control.availability": self.availability.control,
            "control.availability": self.availability.control,
            "safety.loss_of_control": self.safety.loss_of_control,
            "safety.preserved": self.safety.preserved,
            "safety.safe_state_reached": self.safety.safe_state_reached,
            "recovery.mttr": self.recovery.mean_time_to_recovery,
            "recovery.max": self.recovery.max_time_to_recovery,
            "recovery.success_rate": self.recovery.success_rate,
            "recovery.count": self.recovery.faults_recovered,
            "recovery.required": self.recovery.faults_requiring_recovery,
            "recovery.time_to_safe_state": self.recovery.time_to_safe_state,
            "containment.flight_domain_affected": self.propagation.flight_domain_affected,
            "containment.critical_domain_reached": self.propagation.critical_domain_reached,
            "containment.contained": self.propagation.contained,
            "containment.boundary_crossed": self.propagation.boundary_crossed,
            "containment.affected_domains": len(self.propagation.affected_domains),
            "containment.affected_components": len(self.propagation.affected_components),
            "containment.propagated_components": len(self.propagation.propagated_components),
            "containment.propagation_depth": self.propagation.max_propagation_depth,
            "mission.completion": self.mission.completion,
            "mission.continuity": self.mission.continuity,
            "mission.completed": self.mission.completed,
            "mission.duration": self.mission.duration,
            "navigation.integrity": self.availability.navigation_integrity,
            "navigation.availability": self.availability.navigation,
            "communications.availability": self.availability.communications,
            "compute.availability": self.availability.compute,
            "power.availability": self.availability.power,
            "time.nominal": self.modes.time_nominal,
            "time.degraded": self.modes.time_degraded,
            "time.failed": self.modes.time_failed,
            "time.total": self.modes.total,
            "events.injected": self.events.injected,
            "events.applied": self.events.applied,
            "events.rejected": self.events.rejected,
            "events.observed_effects": self.events.observed_effects,
            "events.recoveries": self.events.recoveries,
            "events.expectations_failed": self.events.expectations_failed,
        }
        for subsystem, value in self.recovery.per_subsystem_max.items():
            ctx[f"recovery.{subsystem.replace('.', '_')}"] = value
        return ctx


def _domain_components(topology: SystemTopology, domain: Domain) -> list[str]:
    return [c.id for c in topology.components if c.domain == domain]


def _time_in_state(samples: Sequence[TelemetrySample]) -> dict[str, dict[ComponentState, float]]:
    result: dict[str, dict[ComponentState, float]] = defaultdict(lambda: defaultdict(float))
    for current, nxt in pairwise(samples):
        dt = max(0.0, nxt.t - current.t)
        for subsystem, state in current.health.items():
            result[subsystem][state] += dt
    return result


def _domain_availability(
    samples: Sequence[TelemetrySample], components: list[str], total: float
) -> float:
    if total <= 0 or not samples or not components:
        return 1.0
    healthy_time = 0.0
    for current, nxt in pairwise(samples):
        dt = max(0.0, nxt.t - current.t)
        if all(current.health.get(c, ComponentState.UNKNOWN).is_healthy for c in components):
            healthy_time += dt
    return min(1.0, healthy_time / total)


def _weighted_integrity(samples: Sequence[TelemetrySample], component: str, total: float) -> float:
    if total <= 0 or not samples:
        return 1.0
    score = 0.0
    for current, nxt in pairwise(samples):
        dt = max(0.0, nxt.t - current.t)
        state = current.health.get(component, ComponentState.UNKNOWN)
        if state.is_healthy:
            score += dt
        elif state.is_impaired:
            score += 0.5 * dt
    return min(1.0, score / total)


def compute_metrics(
    *,
    events: Sequence[RunEvent],
    samples: Sequence[TelemetrySample],
    topology: SystemTopology = DEFAULT_TOPOLOGY,
) -> MetricsResult:
    events = sorted(events, key=lambda e: (e.simulation_time, e.sequence))
    samples = sorted(samples, key=lambda s: s.t)
    total = samples[-1].t - samples[0].t if len(samples) >= 2 else 0.0
    if total <= 0 and events:
        total = max(e.simulation_time for e in events)

    # ------------------------------------------------------------- mission
    last = samples[-1] if samples else None
    completion = max((s.mission.progress for s in samples), default=0.0)
    completed = bool(last and last.mission.phase is MissionPhase.COMPLETE)
    time_in_hold = 0.0
    time_in_mission_modes = 0.0
    for current, nxt in pairwise(samples):
        dt = max(0.0, nxt.t - current.t)
        if current.flight.mode in (FlightMode.HOLD, FlightMode.RTL) or (
            current.mission.phase is MissionPhase.HOLDING
        ):
            time_in_hold += dt
        elif current.flight.mode in (FlightMode.MISSION, FlightMode.TAKEOFF, FlightMode.LAND):
            time_in_mission_modes += dt
    continuity = 1.0 if total <= 0 else max(0.0, min(1.0, 1.0 - time_in_hold / total))

    # ------------------------------------------------------------- availability
    availability = AvailabilityMetrics(
        control=_domain_availability(samples, ["flight_control.core"], total),
        navigation_integrity=_weighted_integrity(samples, "navigation.estimator", total),
        navigation=_domain_availability(samples, ["navigation.estimator"], total),
        communications=_domain_availability(
            samples, _domain_components(topology, Domain.COMMUNICATIONS), total
        ),
        compute=_domain_availability(
            samples, _domain_components(topology, Domain.MISSION_COMPUTE), total
        ),
        power=_domain_availability(samples, _domain_components(topology, Domain.POWER), total),
    )

    # ------------------------------------------------------------- recovery
    cleared_reason: dict[str, str] = {}
    cleared_at: dict[str, float] = {}
    cleared_by_subsystem: dict[str, list[float]] = defaultdict(list)
    for e in events:
        if e.kind is EventKind.INJECTION_CLEARED and e.scenario_event_id:
            cleared_reason[e.scenario_event_id] = str(e.metadata.get("reason", ""))
            if e.metadata.get("reason") == "duration elapsed":
                cleared_at[e.scenario_event_id] = e.simulation_time
                if e.subsystem:
                    cleared_by_subsystem[e.subsystem].append(e.simulation_time)
    applied_effects: dict[str, str] = {
        e.scenario_event_id: str(e.metadata.get("effect") or e.metadata.get("mechanism", ""))
        for e in events
        if e.kind is EventKind.INJECTION_APPLIED and e.scenario_event_id
    }
    requested_effects: dict[str, str] = {
        e.scenario_event_id: str(e.metadata.get("effect", ""))
        for e in events
        if e.kind is EventKind.INJECTION_REQUEST and e.scenario_event_id
    }

    open_faults: dict[str, RunEvent] = {}
    records: list[RecoveryRecord] = []
    first_fault_at: float | None = None
    for e in events:
        if e.kind is EventKind.OBSERVED_EFFECT and e.subsystem and e.state_after:
            if e.state_after.is_healthy or e.subsystem in open_faults:
                continue
            open_faults[e.subsystem] = e
            if first_fault_at is None:
                first_fault_at = e.simulation_time
        elif e.kind is EventKind.RECOVERY and e.subsystem and e.subsystem in open_faults:
            opened = open_faults.pop(e.subsystem)
            cause = opened.scenario_event_id
            # The disturbance ends when the last bounded injection acting on this
            # subsystem (directly, or through the attributed cause) is cleared.
            candidates = [cleared_at[cause]] if cause and cause in cleared_at else []
            candidates += [
                t_clear
                for t_clear in cleared_by_subsystem.get(e.subsystem, [])
                if opened.simulation_time <= t_clear <= e.simulation_time
            ]
            disturbance_end = max(candidates) if candidates else None
            reference = opened.simulation_time
            if disturbance_end is not None:
                reference = max(reference, min(disturbance_end, e.simulation_time))
            records.append(
                RecoveryRecord(
                    subsystem=e.subsystem,
                    fault_state=opened.state_after or ComponentState.UNKNOWN,
                    fault_started_at=opened.simulation_time,
                    recovered_at=e.simulation_time,
                    fault_duration=round(e.simulation_time - opened.simulation_time, 3),
                    recovery_time=round(e.simulation_time - reference, 3),
                    disturbance_cleared_at=disturbance_end,
                    caused_by=cause,
                    direct=bool(opened.metadata.get("direct", False)),
                    recovery_expected=True,
                )
            )
    for subsystem, opened in open_faults.items():
        cause = opened.scenario_event_id
        effect = requested_effects.get(cause or "", applied_effects.get(cause or "", ""))
        persisted_to_end = (
            cause is not None
            and (cleared_reason.get(cause) == "scenario end" or cause not in cleared_reason)
            and effect not in {"restart", "crash"}
        )
        records.append(
            RecoveryRecord(
                subsystem=subsystem,
                fault_state=opened.state_after or ComponentState.UNKNOWN,
                fault_started_at=opened.simulation_time,
                recovered_at=None,
                fault_duration=None,
                recovery_time=None,
                disturbance_cleared_at=cleared_at.get(cause) if cause else None,
                caused_by=cause,
                direct=bool(opened.metadata.get("direct", False)),
                recovery_expected=not persisted_to_end,
            )
        )
    required = [r for r in records if r.recovery_expected]
    recovered = [r for r in required if r.recovery_time is not None]
    recovery_times = [r.recovery_time for r in recovered if r.recovery_time is not None]
    per_subsystem_max: dict[str, float] = {}
    for r in recovered:
        if r.recovery_time is not None:
            per_subsystem_max[r.subsystem] = max(
                per_subsystem_max.get(r.subsystem, 0.0), r.recovery_time
            )
    safe_state_events = [
        e
        for e in events
        if e.kind is EventKind.SYSTEM_RESPONSE and bool(e.metadata.get("safe_state"))
    ]
    # Time to safe state: measured from the most recent observed fault that precedes the
    # first safe-state response (the fault that triggered the failsafe).
    time_to_safe_state: float | None = None
    fault_times = [
        e.simulation_time
        for e in events
        if e.kind is EventKind.OBSERVED_EFFECT
        and e.state_after is not None
        and not e.state_after.is_healthy
    ]
    if safe_state_events and fault_times:
        first_safe = safe_state_events[0].simulation_time
        preceding = [ft for ft in fault_times if ft <= first_safe]
        if preceding:
            time_to_safe_state = round(first_safe - max(preceding), 3)
    recovery = RecoveryMetrics(
        records=records,
        mean_time_to_recovery=(
            round(sum(recovery_times) / len(recovery_times), 3) if recovery_times else None
        ),
        max_time_to_recovery=round(max(recovery_times), 3) if recovery_times else None,
        faults_requiring_recovery=len(required),
        faults_recovered=len(recovered),
        success_rate=(len(recovered) / len(required)) if required else None,
        time_to_safe_state=time_to_safe_state,
        safe_state_entered=bool(safe_state_events),
        per_subsystem_max=per_subsystem_max,
    )

    # ------------------------------------------------------------- propagation
    injected = sorted(
        {e.subsystem for e in events if e.kind is EventKind.INJECTION_APPLIED and e.subsystem}
    )
    affected = sorted(
        {
            e.subsystem
            for e in events
            if e.kind is EventKind.OBSERVED_EFFECT
            and e.subsystem
            and e.state_after is not None
            and not e.state_after.is_healthy
        }
    )
    propagated = [c for c in affected if c not in injected]
    depths = topology.propagation_depths(set(injected), set(affected))
    affected_domains = sorted(
        {topology.domain_of(c) for c in affected if topology.has_component(c)},
        key=lambda d: d.value,
    )
    injected_domains = sorted(
        {topology.domain_of(c) for c in injected if topology.has_component(c)},
        key=lambda d: d.value,
    )
    propagated_domains = [d for d in affected_domains if d not in injected_domains]
    critical_reached = any(d in CRITICAL_DOMAINS for d in affected_domains)
    boundary_crossed = False
    for dep in topology.dependencies:
        if dep.crosses_trust_boundary and dep.provider in affected and dep.dependent in affected:
            boundary_crossed = True
    propagation = PropagationMetrics(
        injected_components=injected,
        affected_components=affected,
        propagated_components=propagated,
        affected_domains=affected_domains,
        injected_domains=injected_domains,
        propagated_domains=propagated_domains,
        propagation_count=len(propagated),
        max_propagation_depth=max([d for d in depths.values() if d >= 0], default=0),
        depths=depths,
        critical_domain_reached=critical_reached,
        flight_domain_affected=critical_reached,
        contained=not critical_reached,
        boundary_crossed=boundary_crossed,
    )

    # ------------------------------------------------------------- modes
    critical_ids = topology.critical_component_ids
    mode_time: dict[SystemMode, float] = defaultdict(float)
    for current, nxt in pairwise(samples):
        dt = max(0.0, nxt.t - current.t)
        mode_time[aggregate_system_mode(current.health, critical_ids)] += dt
    modes = ModeMetrics(
        time_nominal=round(mode_time[SystemMode.NOMINAL], 3),
        time_degraded=round(mode_time[SystemMode.DEGRADED], 3),
        time_failed=round(mode_time[SystemMode.FAILED], 3),
        total=round(total, 3),
    )

    # ------------------------------------------------------------- safety
    time_in_state = _time_in_state(samples)
    fc_states = time_in_state.get("flight_control.core", {})
    fc_unhealthy_time = sum(v for s, v in fc_states.items() if not s.is_healthy)
    fc_failed_event = any(
        e.kind is EventKind.OBSERVED_EFFECT
        and e.subsystem == "flight_control.core"
        and e.state_after is not None
        and not e.state_after.is_healthy
        for e in events
    )
    loss_of_control = any(not s.flight.control_authority for s in samples) or any(
        s.health.get("flight_control.core") is ComponentState.FAILED for s in samples
    )
    flight_control_available = fc_unhealthy_time <= 0.0 and not fc_failed_event
    safety = SafetyMetrics(
        loss_of_control=loss_of_control,
        control_availability=availability.control,
        flight_control_available=flight_control_available,
        preserved=(not loss_of_control) and flight_control_available,
        safe_state_reached=bool(safe_state_events),
    )

    # ------------------------------------------------------------- events
    def count(kind: EventKind) -> int:
        return sum(1 for e in events if e.kind is kind)

    counts = EventCounts(
        injected=count(EventKind.INJECTION_REQUEST),
        applied=count(EventKind.INJECTION_APPLIED),
        rejected=count(EventKind.INJECTION_REJECTED),
        cleared=count(EventKind.INJECTION_CLEARED),
        observed_effects=count(EventKind.OBSERVED_EFFECT),
        system_responses=count(EventKind.SYSTEM_RESPONSE),
        recoveries=count(EventKind.RECOVERY),
        expectations_passed=sum(
            1 for e in events if e.kind is EventKind.EXPECTATION_RESULT and e.metadata.get("passed")
        ),
        expectations_failed=sum(
            1
            for e in events
            if e.kind is EventKind.EXPECTATION_RESULT and not e.metadata.get("passed")
        ),
        degraded_transitions=sum(
            1
            for e in events
            if e.kind is EventKind.OBSERVED_EFFECT and e.state_after is ComponentState.DEGRADED
        ),
        failed_transitions=sum(
            1
            for e in events
            if e.kind is EventKind.OBSERVED_EFFECT
            and e.state_after in (ComponentState.FAILED, ComponentState.UNAVAILABLE)
        ),
    )

    final_states: dict[str, ComponentState] = dict(last.health) if last else {}

    return MetricsResult(
        run_duration=round(total, 3),
        sample_count=len(samples),
        mission=MissionMetrics(
            completion=round(completion, 4),
            continuity=round(continuity, 4),
            completed=completed,
            duration=round(total, 3),
            time_in_hold=round(time_in_hold, 3),
            time_in_mission_modes=round(time_in_mission_modes, 3),
        ),
        availability=availability,
        recovery=recovery,
        propagation=propagation,
        modes=modes,
        safety=safety,
        events=counts,
        component_time_in_state={
            subsystem: {state.value: round(seconds, 3) for state, seconds in states.items()}
            for subsystem, states in time_in_state.items()
        },
        final_component_states=final_states,
    )

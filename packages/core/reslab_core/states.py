"""Central definitions of every state vocabulary used by the platform.

Nothing outside this module should introduce new state strings. The frontend
consumes the same vocabulary through the OpenAPI schema.
"""

from __future__ import annotations

from enum import StrEnum


class ComponentState(StrEnum):
    """Observed operating state of a system component or subsystem.

    Semantics:

    - `NOMINAL`: performing within specification, no active fault. Used for sensors,
      navigation, communications and power components.
    - `OPERATIONAL`: performing its function. Used for flight control, actuation and
      compute components where "operational" is the natural vocabulary. Equivalent to
      `NOMINAL` for every calculation.
    - `DEGRADED`: still performing its function with reduced quality, capacity or
      confidence (for example navigation without GNSS aiding).
    - `UNAVAILABLE`: the function is not being provided (link lost, sensor silent) but
      the component itself did not fail.
    - `FAILED`: the component itself failed (crash, fault latch, loss of control).
    - `RECOVERING`: a recovery action is in progress (process restart, re-acquisition).
    - `RECOVERED`: back to a healthy state after a fault. Behaves as healthy for every
      availability calculation; kept distinct so timelines show the recovery.
    - `UNKNOWN`: no observation is available for this component.
    """

    NOMINAL = "NOMINAL"
    OPERATIONAL = "OPERATIONAL"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"
    RECOVERED = "RECOVERED"
    UNKNOWN = "UNKNOWN"

    @property
    def is_healthy(self) -> bool:
        return self in HEALTHY_STATES

    @property
    def is_impaired(self) -> bool:
        return self is ComponentState.DEGRADED

    @property
    def is_down(self) -> bool:
        return self in DOWN_STATES


HEALTHY_STATES: frozenset[ComponentState] = frozenset(
    {ComponentState.NOMINAL, ComponentState.OPERATIONAL, ComponentState.RECOVERED}
)
DOWN_STATES: frozenset[ComponentState] = frozenset(
    {ComponentState.UNAVAILABLE, ComponentState.FAILED, ComponentState.RECOVERING}
)


class SystemMode(StrEnum):
    """Aggregated operating mode of the whole system at an instant.

    - `NOMINAL`: every observed component is healthy.
    - `DEGRADED`: at least one component is degraded or unavailable, but no
      flight-critical component is down and no component has failed.
    - `FAILED`: a component has failed, or a flight-critical component is down.
    """

    NOMINAL = "NOMINAL"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class FlightMode(StrEnum):
    """Vehicle-level operating mode reported by the adapter."""

    IDLE = "IDLE"
    TAKEOFF = "TAKEOFF"
    MISSION = "MISSION"
    HOLD = "HOLD"
    RTL = "RTL"
    LAND = "LAND"
    LANDED = "LANDED"
    UNKNOWN = "UNKNOWN"


SAFE_STATE_MODES: frozenset[FlightMode] = frozenset(
    {FlightMode.HOLD, FlightMode.RTL, FlightMode.LAND, FlightMode.LANDED}
)


class MissionPhase(StrEnum):
    PENDING = "PENDING"
    TAKEOFF = "TAKEOFF"
    ENROUTE = "ENROUTE"
    HOLDING = "HOLDING"
    RETURNING = "RETURNING"
    LANDING = "LANDING"
    COMPLETE = "COMPLETE"
    ABORTED = "ABORTED"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


class EventKind(StrEnum):
    """Scientific classification of a run event.

    The distinction matters: a requested disturbance is not evidence that the
    system was actually disturbed, and an expected response is not evidence that
    it happened.

    - `INJECTION_REQUEST`: the scenario engine asked the adapter to inject an effect.
    - `INJECTION_APPLIED`: the adapter confirmed the effect is active in the target.
    - `INJECTION_REJECTED`: the adapter could not apply the effect.
    - `INJECTION_CLEARED`: the effect was removed (duration elapsed or scenario end).
    - `OBSERVED_EFFECT`: a component state change observed in the target.
    - `SYSTEM_RESPONSE`: an autonomous reaction of the target (mode change, failsafe).
    - `RECOVERY`: a component returned to a healthy state.
    - `EXPECTATION_RESULT`: an expected behaviour declared in the scenario was checked.
    - `ASSERTION_RESULT`: a scenario assertion was evaluated during analysis.
    - `MISSION`: mission progress (waypoint reached, mission complete).
    - `LIFECYCLE`: run lifecycle transition.
    - `LOG`: informational message from a component.
    """

    INJECTION_REQUEST = "INJECTION_REQUEST"
    INJECTION_APPLIED = "INJECTION_APPLIED"
    INJECTION_REJECTED = "INJECTION_REJECTED"
    INJECTION_CLEARED = "INJECTION_CLEARED"
    OBSERVED_EFFECT = "OBSERVED_EFFECT"
    SYSTEM_RESPONSE = "SYSTEM_RESPONSE"
    RECOVERY = "RECOVERY"
    EXPECTATION_RESULT = "EXPECTATION_RESULT"
    ASSERTION_RESULT = "ASSERTION_RESULT"
    MISSION = "MISSION"
    LIFECYCLE = "LIFECYCLE"
    LOG = "LOG"


class EventSource(StrEnum):
    SCENARIO = "scenario"
    ADAPTER = "adapter"
    ENGINE = "engine"
    ANALYSIS = "analysis"
    PLATFORM = "platform"


class RunState(StrEnum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    RECOVERING = "RECOVERING"
    COLLECTING = "COLLECTING"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_RUN_STATES

    @property
    def is_active(self) -> bool:
        return self in ACTIVE_RUN_STATES


TERMINAL_RUN_STATES: frozenset[RunState] = frozenset(
    {RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED}
)
ACTIVE_RUN_STATES: frozenset[RunState] = frozenset(
    {RunState.PREPARING, RunState.RUNNING, RunState.RECOVERING, RunState.COLLECTING}
)

RUN_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset({RunState.VALIDATING, RunState.CANCELLED}),
    RunState.VALIDATING: frozenset({RunState.QUEUED, RunState.FAILED, RunState.CANCELLED}),
    RunState.QUEUED: frozenset({RunState.PREPARING, RunState.FAILED, RunState.CANCELLED}),
    RunState.PREPARING: frozenset({RunState.RUNNING, RunState.FAILED, RunState.CANCELLED}),
    RunState.RUNNING: frozenset(
        {RunState.RECOVERING, RunState.COLLECTING, RunState.FAILED, RunState.CANCELLED}
    ),
    RunState.RECOVERING: frozenset(
        {RunState.RUNNING, RunState.COLLECTING, RunState.FAILED, RunState.CANCELLED}
    ),
    RunState.COLLECTING: frozenset({RunState.ANALYZING, RunState.FAILED, RunState.CANCELLED}),
    RunState.ANALYZING: frozenset({RunState.COMPLETED, RunState.FAILED}),
    RunState.COMPLETED: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
}


class InvalidRunTransitionError(Exception):
    def __init__(self, current: RunState, target: RunState) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid run transition {current.value} -> {target.value}")


def can_transition(current: RunState, target: RunState) -> bool:
    return target in RUN_TRANSITIONS[current]


def transition(current: RunState, target: RunState) -> RunState:
    """Return `target` if the transition is legal, otherwise raise.

    Invalid transitions never silently succeed.
    """

    if not can_transition(current, target):
        raise InvalidRunTransitionError(current, target)
    return target


class BenchmarkResult(StrEnum):
    """Outcome of a run once analyzed.

    `passed` and `failed` are only emitted for runs that completed their scenario.
    `inconclusive` marks runs that could not be fully executed or analyzed.
    """

    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class AssertionOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"


def aggregate_system_mode(
    states: dict[str, ComponentState], critical_components: frozenset[str]
) -> SystemMode:
    """Compute the aggregated system mode from a map of component states.

    `critical_components` are the components whose loss means loss of the
    flight-critical function (flight control core, actuation).
    """

    mode = SystemMode.NOMINAL
    for component_id, state in states.items():
        if state is ComponentState.FAILED:
            return SystemMode.FAILED
        if state.is_down and component_id in critical_components:
            return SystemMode.FAILED
        if state.is_impaired or state.is_down:
            mode = SystemMode.DEGRADED
    return mode

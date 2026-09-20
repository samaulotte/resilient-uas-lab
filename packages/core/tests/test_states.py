from __future__ import annotations

import pytest

from reslab_core.states import (
    RUN_TRANSITIONS,
    ComponentState,
    InvalidRunTransitionError,
    RunState,
    SystemMode,
    aggregate_system_mode,
    can_transition,
    transition,
)


def test_nominal_lifecycle_path_is_valid() -> None:
    path = [
        RunState.CREATED,
        RunState.VALIDATING,
        RunState.QUEUED,
        RunState.PREPARING,
        RunState.RUNNING,
        RunState.RECOVERING,
        RunState.RUNNING,
        RunState.COLLECTING,
        RunState.ANALYZING,
        RunState.COMPLETED,
    ]
    current = path[0]
    for nxt in path[1:]:
        current = transition(current, nxt)
    assert current is RunState.COMPLETED
    assert current.is_terminal


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunState.CREATED, RunState.RUNNING),
        (RunState.QUEUED, RunState.COMPLETED),
        (RunState.COMPLETED, RunState.RUNNING),
        (RunState.FAILED, RunState.QUEUED),
        (RunState.CANCELLED, RunState.CANCELLED),
        (RunState.ANALYZING, RunState.CANCELLED),
        (RunState.RUNNING, RunState.ANALYZING),
    ],
)
def test_invalid_transitions_raise(current: RunState, target: RunState) -> None:
    assert not can_transition(current, target)
    with pytest.raises(InvalidRunTransitionError):
        transition(current, target)


def test_terminal_states_have_no_outgoing_transitions() -> None:
    for state in (RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED):
        assert RUN_TRANSITIONS[state] == frozenset()


def test_every_non_terminal_state_can_fail_or_cancel() -> None:
    for state, targets in RUN_TRANSITIONS.items():
        if state.is_terminal:
            continue
        assert RunState.FAILED in targets or RunState.CANCELLED in targets


def test_component_state_classes() -> None:
    assert ComponentState.NOMINAL.is_healthy
    assert ComponentState.OPERATIONAL.is_healthy
    assert ComponentState.RECOVERED.is_healthy
    assert ComponentState.DEGRADED.is_impaired
    assert ComponentState.UNAVAILABLE.is_down
    assert ComponentState.RECOVERING.is_down
    assert not ComponentState.UNKNOWN.is_healthy


def test_aggregate_system_mode() -> None:
    critical = frozenset({"flight_control.core"})
    assert aggregate_system_mode({"a": ComponentState.NOMINAL}, critical) is SystemMode.NOMINAL
    assert (
        aggregate_system_mode({"navigation.gnss": ComponentState.UNAVAILABLE}, critical)
        is SystemMode.DEGRADED
    )
    assert (
        aggregate_system_mode({"flight_control.core": ComponentState.UNAVAILABLE}, critical)
        is SystemMode.FAILED
    )
    assert aggregate_system_mode({"x": ComponentState.FAILED}, critical) is SystemMode.FAILED

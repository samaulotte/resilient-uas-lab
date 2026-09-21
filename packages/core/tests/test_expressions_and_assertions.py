from __future__ import annotations

import pytest

from reslab_core.analysis.assertions import evaluate_assertion
from reslab_core.analysis.expressions import ExpressionError, Operator, parse_expression
from reslab_core.scenario.model import Assertion
from reslab_core.states import AssertionOutcome, Severity


def test_parse_boolean_expression() -> None:
    expr = parse_expression("flight_control.available == true")
    assert expr.path == "flight_control.available"
    assert expr.operator is Operator.EQ
    assert expr.value is True


def test_parse_duration_and_percentage_literals() -> None:
    assert parse_expression("recovery.mission_compute < 10s").value == 10.0
    assert parse_expression("mission.completion >= 80%").value == pytest.approx(0.8)
    assert parse_expression("mission.completion >= 0.80").value == pytest.approx(0.8)


@pytest.mark.parametrize(
    "text",
    [
        "flight_control.available",
        "mission.completion => 1",
        "mission.completion >= abc",
        "__import__('os') == 1",
        "mission.completion == 1; drop table",
        "unknown.metric == 1",
        "flight_control.available > true",
        "mission == 1",
    ],
)
def test_parse_rejects_invalid(text: str) -> None:
    with pytest.raises(ExpressionError):
        parse_expression(text)


def test_evaluate_numeric_operators() -> None:
    assert parse_expression("recovery.mttr < 10s").evaluate(4.2)
    assert not parse_expression("recovery.mttr < 10s").evaluate(12.0)
    assert parse_expression("mission.completion >= 0.8").evaluate(0.8)
    assert parse_expression("containment.affected_domains != 0").evaluate(2)
    assert not parse_expression("recovery.mttr < 10s").evaluate(None)


def test_evaluate_boolean_type_mismatch_fails() -> None:
    assert not parse_expression("safety.loss_of_control == false").evaluate(0.0)
    assert parse_expression("safety.loss_of_control == false").evaluate(False)


def test_assertion_result_has_measured_and_explanation() -> None:
    assertion = Assertion(expression="recovery.mission_compute < 10s", severity=Severity.HIGH)
    result = evaluate_assertion(assertion, {"recovery.mission_compute": 4.9}, simulation_time=120.0)
    assert result.outcome is AssertionOutcome.PASSED
    assert result.measured == 4.9
    assert result.expected == 10.0
    assert "4.9s" in result.explanation
    assert result.simulation_time == 120.0


def test_assertion_not_evaluated_when_metric_missing() -> None:
    assertion = Assertion(expression="recovery.mission_compute < 10s")
    result = evaluate_assertion(assertion, {})
    assert result.outcome is AssertionOutcome.NOT_EVALUATED


def test_assertion_not_evaluated_when_metric_never_measured() -> None:
    # A metric that exists in the model but was never observed (value None) cannot be
    # evaluated. It must be NOT_EVALUATED, never silently treated as a pass or a fail.
    assertion = Assertion(expression="recovery.mission_compute < 10s")
    result = evaluate_assertion(assertion, {"recovery.mission_compute": None})
    assert result.outcome is AssertionOutcome.NOT_EVALUATED
    assert "never observed" in result.explanation

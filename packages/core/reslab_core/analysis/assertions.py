"""Evaluation of scenario assertions against the metric context."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from reslab_core.analysis.expressions import Expression, parse_expression
from reslab_core.duration import format_duration
from reslab_core.scenario.model import Assertion
from reslab_core.states import AssertionOutcome, Severity


class AssertionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    expression: str
    severity: Severity
    description: str = ""
    outcome: AssertionOutcome
    measured: float | bool | int | None = Field(description="Value observed for the metric path")
    expected: float | bool = Field(description="Literal the metric was compared against")
    operator: str
    metric_path: str
    explanation: str
    simulation_time: float | None = Field(
        default=None, description="Simulation time at which the metric was finalized"
    )


def _format(value: float | bool | int | None, hint: str) -> str:
    if value is None:
        return "not measured"
    if isinstance(value, bool):
        return str(value).lower()
    if hint.endswith(("s", "ms")) and hint[:-1].replace(".", "").isdigit():
        return format_duration(float(value))
    if hint.endswith("%"):
        return f"{float(value) * 100:.1f}%"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".") or "0"
    return str(value)


def evaluate_assertion(
    assertion: Assertion,
    context: dict[str, float | bool | int | None],
    *,
    simulation_time: float | None = None,
) -> AssertionResult:
    expression: Expression = parse_expression(assertion.expression)
    measured = context.get(expression.path)
    known = expression.path in context
    if not known:
        outcome = AssertionOutcome.NOT_EVALUATED
        explanation = f"metric '{expression.path}' is not available for this run"
    elif measured is None:
        # The metric exists in the model but was never observed during the run (for
        # example a recovery time when nothing recovered, or a state that stayed UNKNOWN
        # because the link was down). The assertion cannot be evaluated; it must not be
        # silently treated as a pass or a fail.
        outcome = AssertionOutcome.NOT_EVALUATED
        explanation = (
            f"{expression.path} was never observed during the run; "
            "the assertion could not be evaluated"
        )
    else:
        passed = expression.evaluate(measured)
        outcome = AssertionOutcome.PASSED if passed else AssertionOutcome.FAILED
        explanation = (
            f"measured {expression.path} = {_format(measured, expression.raw_value)}, "
            f"expected {expression.operator.value} {expression.raw_value}"
        )
    return AssertionResult(
        expression=assertion.expression,
        severity=assertion.severity,
        description=assertion.description,
        outcome=outcome,
        measured=measured,
        expected=expression.value,
        operator=expression.operator.value,
        metric_path=expression.path,
        explanation=explanation,
        simulation_time=simulation_time,
    )


def evaluate_assertions(
    assertions: list[Assertion],
    context: dict[str, float | bool | int | None],
    *,
    simulation_time: float | None = None,
) -> list[AssertionResult]:
    return [evaluate_assertion(a, context, simulation_time=simulation_time) for a in assertions]

"""Transparent, configurable resilience scoring.

A score profile assigns integer weights (summing to 100) to named dimensions. Each
dimension is a value in [0, 1] derived from documented metrics. The total is the
weighted sum on a 0-100 scale.

Hard gates override the numeric score: a benchmark whose critical assertion failed,
or during which control was lost, is `failed` no matter how high the number is.
"""

from __future__ import annotations

from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from reslab_core.analysis.assertions import AssertionResult
from reslab_core.analysis.metrics import MetricsResult
from reslab_core.states import AssertionOutcome, BenchmarkResult, Severity

DIMENSIONS: tuple[str, ...] = (
    "safety",
    "mission_continuity",
    "recovery",
    "containment",
    "navigation",
    "communications",
    "compute",
)

DIMENSION_LABELS: dict[str, str] = {
    "safety": "Safety preservation",
    "mission_continuity": "Mission continuity",
    "recovery": "Recovery capability",
    "containment": "Fault containment",
    "navigation": "Navigation integrity",
    "communications": "Communications",
    "compute": "Compute availability",
}


class ScoreParameters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mttr_target: float = Field(default=5.0, gt=0, description="Recovery time scoring 1.0 (s)")
    mttr_limit: float = Field(default=30.0, gt=0, description="Recovery time scoring 0.0 (s)")
    containment_penalty_per_domain: float = Field(default=0.25, ge=0, le=1)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.mttr_limit <= self.mttr_target:
            raise ValueError("mttr_limit must be greater than mttr_target")
        return self


class ScoreProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    description: str = ""
    weights: dict[str, int] = Field(description="Dimension weights, must sum to 100")
    parameters: ScoreParameters = Field(default_factory=ScoreParameters)

    @model_validator(mode="after")
    def _weights(self) -> Self:
        unknown = set(self.weights) - set(DIMENSIONS)
        if unknown:
            raise ValueError(f"unknown score dimensions: {', '.join(sorted(unknown))}")
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("weights must be non-negative")
        total = sum(self.weights.values())
        if total != 100:
            raise ValueError(f"weights must sum to 100, got {total}")
        return self


DEFAULT_SCORE_PROFILE = ScoreProfile(
    name="default",
    description=(
        "Balanced profile for autonomous flight: safety first, then mission continuity "
        "and recovery, then containment and navigation, then communications."
    ),
    weights={
        "safety": 30,
        "mission_continuity": 20,
        "recovery": 20,
        "containment": 15,
        "navigation": 10,
        "communications": 5,
        "compute": 0,
    },
)


def load_score_profile(path: str | Path) -> ScoreProfile:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("score profile must be a mapping")
    profile = data.get("score_profile", data)
    return ScoreProfile.model_validate(profile)


class DimensionScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    label: str
    weight: int
    score: float = Field(ge=0, le=1, description="Normalized dimension score")
    points: float = Field(description="score * weight")
    explanation: str


class HardGate(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    reason: str


class ScoreResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile: ScoreProfile
    total: float = Field(ge=0, le=100)
    dimensions: list[DimensionScore]
    hard_gates: list[HardGate]
    hard_gate_result: BenchmarkResult
    result: BenchmarkResult
    reason: str


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _recovery_score(metrics: MetricsResult, params: ScoreParameters) -> tuple[float, str]:
    rec = metrics.recovery
    if rec.faults_requiring_recovery == 0:
        return 1.0, "no fault required recovery"
    success = rec.success_rate or 0.0
    if rec.mean_time_to_recovery is None:
        return 0.0, f"{rec.faults_recovered}/{rec.faults_requiring_recovery} recovered"
    mttr = rec.mean_time_to_recovery
    if mttr <= params.mttr_target:
        speed = 1.0
    elif mttr >= params.mttr_limit:
        speed = 0.0
    else:
        speed = 1.0 - (mttr - params.mttr_target) / (params.mttr_limit - params.mttr_target)
    return _clamp(success * speed), (
        f"{rec.faults_recovered}/{rec.faults_requiring_recovery} recovered, "
        f"MTTR {mttr:.1f}s (target {params.mttr_target:.0f}s, limit {params.mttr_limit:.0f}s)"
    )


def _containment_score(metrics: MetricsResult, params: ScoreParameters) -> tuple[float, str]:
    prop = metrics.propagation
    if prop.critical_domain_reached:
        return 0.0, "fault reached the flight-critical domain"
    penalty = params.containment_penalty_per_domain * len(prop.propagated_domains)
    domains = ", ".join(d.value for d in prop.propagated_domains) or "none"
    return _clamp(
        1.0 - penalty
    ), f"propagated to {len(prop.propagated_domains)} domain(s): {domains}"


def compute_score(
    metrics: MetricsResult,
    assertions: list[AssertionResult],
    profile: ScoreProfile = DEFAULT_SCORE_PROFILE,
    *,
    run_completed: bool = True,
) -> ScoreResult:
    params = profile.parameters
    safety_score = 0.0 if metrics.safety.loss_of_control else metrics.availability.control
    values: dict[str, tuple[float, str]] = {
        "safety": (
            _clamp(safety_score),
            "loss of control"
            if metrics.safety.loss_of_control
            else (f"flight control available {metrics.availability.control * 100:.1f}% of the run"),
        ),
        "mission_continuity": (
            _clamp(0.5 * metrics.mission.completion + 0.5 * metrics.mission.continuity),
            f"completion {metrics.mission.completion * 100:.1f}%, "
            f"continuity {metrics.mission.continuity * 100:.1f}%",
        ),
        "recovery": _recovery_score(metrics, params),
        "containment": _containment_score(metrics, params),
        "navigation": (
            _clamp(metrics.availability.navigation_integrity),
            f"navigation integrity {metrics.availability.navigation_integrity * 100:.1f}%",
        ),
        "communications": (
            _clamp(metrics.availability.communications),
            f"communications available {metrics.availability.communications * 100:.1f}%",
        ),
        "compute": (
            _clamp(metrics.availability.compute),
            f"mission compute available {metrics.availability.compute * 100:.1f}%",
        ),
    }
    dimensions: list[DimensionScore] = []
    total = 0.0
    for dimension in DIMENSIONS:
        weight = profile.weights.get(dimension, 0)
        score, explanation = values[dimension]
        points = round(score * weight, 2)
        total += points
        dimensions.append(
            DimensionScore(
                dimension=dimension,
                label=DIMENSION_LABELS[dimension],
                weight=weight,
                score=round(score, 4),
                points=points,
                explanation=explanation,
            )
        )
    total = round(min(100.0, max(0.0, total)), 1)

    gates: list[HardGate] = []
    failed_critical = [
        a
        for a in assertions
        if a.severity is Severity.CRITICAL and a.outcome is AssertionOutcome.FAILED
    ]
    unevaluated_critical = [
        a
        for a in assertions
        if a.severity is Severity.CRITICAL and a.outcome is AssertionOutcome.NOT_EVALUATED
    ]
    gates.append(
        HardGate(
            name="critical_assertions",
            passed=not failed_critical,
            reason=(
                "all critical assertions passed"
                if not failed_critical
                else "critical assertion violated: "
                + "; ".join(a.expression for a in failed_critical)
            ),
        )
    )
    gates.append(
        HardGate(
            name="control_authority",
            passed=not metrics.safety.loss_of_control,
            reason="control authority preserved"
            if not metrics.safety.loss_of_control
            else "loss of control observed",
        )
    )
    gates.append(
        HardGate(
            name="run_completed",
            passed=run_completed,
            reason="run executed to completion" if run_completed else "run did not complete",
        )
    )
    # Result precedence:
    #   1. run did not complete            -> INCONCLUSIVE
    #   2. positive failure (a critical assertion failed, or loss of control) -> FAILED
    #   3. a critical assertion could not be evaluated (missing observation)  -> INCONCLUSIVE
    #   4. otherwise                        -> PASSED
    # A positive failure always wins over an unevaluable assertion: we have evidence the
    # run failed. INCONCLUSIVE is never reported as a pass.
    positive_failure = bool(failed_critical) or metrics.safety.loss_of_control
    if not run_completed:
        hard_gate_result = BenchmarkResult.INCONCLUSIVE
        result = BenchmarkResult.INCONCLUSIVE
        reason = "run did not complete; result is inconclusive"
    elif positive_failure:
        hard_gate_result = BenchmarkResult.FAILED
        result = BenchmarkResult.FAILED
        reason = "; ".join(g.reason for g in gates if not g.passed)
    elif unevaluated_critical:
        hard_gate_result = BenchmarkResult.INCONCLUSIVE
        result = BenchmarkResult.INCONCLUSIVE
        reason = "critical assertion could not be evaluated: " + "; ".join(
            a.expression for a in unevaluated_critical
        )
    else:
        hard_gate_result = BenchmarkResult.PASSED
        result = BenchmarkResult.PASSED
        reason = "all hard gates passed"
    return ScoreResult(
        profile=profile,
        total=total,
        dimensions=dimensions,
        hard_gates=gates,
        hard_gate_result=hard_gate_result,
        result=result,
        reason=reason,
    )

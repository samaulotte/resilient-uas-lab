"""Two-run comparison with explicit metric semantics.

A numeric change is only called an improvement or a regression when the metric
definition says which direction is better. Neutral metrics are reported as changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from reslab_api.schemas import (
    AssertionComparison,
    CompareResponse,
    DimensionComparison,
    MetricComparison,
)
from reslab_api.services.runs import run_summary
from reslab_core.analysis.scoring import DIMENSION_LABELS, DIMENSIONS
from reslab_core.states import EventKind
from reslab_platform.db import Run, repository

Better = Literal["higher", "lower", "neutral"]
Unit = Literal["percent", "seconds", "count", "score", "bool"]


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    unit: Unit
    better: Better
    tolerance: float = 0.0


METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition("mission.completion", "Mission completion", "percent", "higher", 0.005),
    MetricDefinition("mission.continuity", "Mission continuity", "percent", "higher", 0.005),
    MetricDefinition("control.availability", "Control availability", "percent", "higher", 0.001),
    MetricDefinition("navigation.integrity", "Navigation integrity", "percent", "higher", 0.005),
    MetricDefinition(
        "communications.availability", "Communication availability", "percent", "higher", 0.005
    ),
    MetricDefinition("compute.availability", "Compute availability", "percent", "higher", 0.005),
    MetricDefinition("recovery.mttr", "Mean time to recovery", "seconds", "lower", 0.2),
    MetricDefinition("recovery.max", "Max time to recovery", "seconds", "lower", 0.2),
    MetricDefinition("recovery.success_rate", "Recovery success rate", "percent", "higher", 0.0),
    MetricDefinition("recovery.time_to_safe_state", "Time to safe state", "seconds", "lower", 0.2),
    MetricDefinition("containment.affected_domains", "Affected domains", "count", "lower"),
    MetricDefinition(
        "containment.propagated_components", "Propagated components", "count", "lower"
    ),
    MetricDefinition("containment.propagation_depth", "Max propagation depth", "count", "lower"),
    MetricDefinition("containment.contained", "Fault contained", "bool", "higher"),
    MetricDefinition("safety.loss_of_control", "Loss of control", "bool", "lower"),
    MetricDefinition("safety.preserved", "Safety preserved", "bool", "higher"),
    MetricDefinition("time.degraded", "Time in degraded mode", "seconds", "lower", 0.5),
    MetricDefinition("time.failed", "Time in failed mode", "seconds", "lower", 0.0),
    MetricDefinition("mission.duration", "Mission duration", "seconds", "neutral", 0.5),
    MetricDefinition("events.injected", "Faults requested", "count", "neutral"),
    MetricDefinition("events.applied", "Faults applied", "count", "neutral"),
    MetricDefinition("events.observed_effects", "Observed effects", "count", "neutral"),
)


def _verdict(
    definition: MetricDefinition,
    baseline: float | bool | int | None,
    candidate: float | bool | int | None,
) -> tuple[float | None, str]:
    if baseline is None or candidate is None:
        return None, "not_comparable"
    if isinstance(baseline, bool) or isinstance(candidate, bool):
        if baseline == candidate:
            return None, "unchanged"
        if definition.better == "neutral":
            return None, "changed"
        candidate_better = (
            (candidate is True) if definition.better == "higher" else (candidate is False)
        )
        return None, "improvement" if candidate_better else "regression"
    delta = float(candidate) - float(baseline)
    if abs(delta) <= definition.tolerance:
        return round(delta, 4), "unchanged"
    if definition.better == "neutral":
        return round(delta, 4), "changed"
    improved = delta > 0 if definition.better == "higher" else delta < 0
    return round(delta, 4), "improvement" if improved else "regression"


async def compare_runs(session: AsyncSession, baseline: Run, candidate: Run) -> CompareResponse:
    base_metrics = await repository.get_metrics(session, baseline.id)
    cand_metrics = await repository.get_metrics(session, candidate.id)
    base_ctx = dict(base_metrics.context) if base_metrics else {}
    cand_ctx = dict(cand_metrics.context) if cand_metrics else {}

    metrics: list[MetricComparison] = []
    definitions = list(METRIC_DEFINITIONS)
    recovery_keys = sorted(
        {
            k
            for k in [*base_ctx, *cand_ctx]
            if k.startswith("recovery.")
            and k.split(".", 1)[1]
            not in {"mttr", "max", "success_rate", "count", "required", "time_to_safe_state"}
        }
    )
    for key in recovery_keys:
        definitions.append(
            MetricDefinition(
                key, f"Recovery: {key.split('.', 1)[1].replace('_', ' ')}", "seconds", "lower", 0.2
            )
        )
    for definition in definitions:
        b = base_ctx.get(definition.key)
        c = cand_ctx.get(definition.key)
        if b is None and c is None:
            continue
        delta, verdict = _verdict(definition, b, c)
        metrics.append(
            MetricComparison(
                key=definition.key,
                label=definition.label,
                unit=definition.unit,
                better=definition.better,
                baseline=b,
                candidate=c,
                delta=delta,
                verdict=verdict,  # type: ignore[arg-type]
            )
        )

    dimensions: list[DimensionComparison] = []
    base_dims = {
        d["dimension"]: d
        for d in (base_metrics.score.get("dimensions", []) if base_metrics else [])
    }
    cand_dims = {
        d["dimension"]: d
        for d in (cand_metrics.score.get("dimensions", []) if cand_metrics else [])
    }
    for dimension in DIMENSIONS:
        bd, cd = base_dims.get(dimension), cand_dims.get(dimension)
        weight = int((cd or bd or {}).get("weight", 0))
        if weight == 0:
            continue
        b = float(bd["points"]) if bd else None
        c = float(cd["points"]) if cd else None
        if b is None or c is None:
            verdict = "not_comparable"
            delta = None
        else:
            delta = round(c - b, 2)
            verdict = (
                "unchanged" if abs(delta) < 0.05 else ("improvement" if delta > 0 else "regression")
            )
        dimensions.append(
            DimensionComparison(
                dimension=dimension,
                label=DIMENSION_LABELS[dimension],
                weight=weight,
                baseline=b,
                candidate=c,
                delta=delta,
                verdict=verdict,  # type: ignore[arg-type]
            )
        )
    metrics.insert(
        0,
        MetricComparison(
            key="score.total",
            label="Resilience score",
            unit="score",
            better="higher",
            baseline=baseline.resilience_score,
            candidate=candidate.resilience_score,
            delta=(
                round(candidate.resilience_score - baseline.resilience_score, 2)
                if baseline.resilience_score is not None and candidate.resilience_score is not None
                else None
            ),
            verdict=(
                "not_comparable"
                if baseline.resilience_score is None or candidate.resilience_score is None
                else (
                    "unchanged"
                    if abs(candidate.resilience_score - baseline.resilience_score) < 0.05
                    else (
                        "improvement"
                        if candidate.resilience_score > baseline.resilience_score
                        else "regression"
                    )
                )
            ),
        ),
    )

    base_assertions = {
        a.expression: a for a in await repository.list_assertions(session, baseline.id)
    }
    cand_assertions = {
        a.expression: a for a in await repository.list_assertions(session, candidate.id)
    }
    assertions: list[AssertionComparison] = []
    for expression in sorted(set(base_assertions) | set(cand_assertions)):
        ba, ca = base_assertions.get(expression), cand_assertions.get(expression)
        b_out = ba.outcome if ba else None
        c_out = ca.outcome if ca else None
        if b_out is None or c_out is None:
            verdict = "not_comparable"
        elif b_out == c_out:
            verdict = "unchanged"
        elif c_out == "passed":
            verdict = "improvement"
        elif c_out == "failed":
            verdict = "regression"
        else:
            verdict = "changed"
        assertions.append(
            AssertionComparison(
                expression=expression,
                severity=(ca or ba).severity if (ca or ba) else "medium",
                baseline=b_out,
                candidate=c_out,
                verdict=verdict,  # type: ignore[arg-type]
            )
        )

    base_events = [
        e
        for e in await repository.list_events(session, baseline.id, limit=2000)
        if e.kind is not EventKind.LOG
    ]
    cand_events = [
        e
        for e in await repository.list_events(session, candidate.id, limit=2000)
        if e.kind is not EventKind.LOG
    ]

    regressions = sum(1 for m in metrics if m.verdict == "regression") + sum(
        1 for a in assertions if a.verdict == "regression"
    )
    improvements = sum(1 for m in metrics if m.verdict == "improvement") + sum(
        1 for a in assertions if a.verdict == "improvement"
    )
    if base_metrics is None or cand_metrics is None:
        overall = "not_comparable"
    elif regressions and improvements:
        overall = "mixed"
    elif regressions:
        overall = "regression"
    elif improvements:
        overall = "improvement"
    else:
        overall = "unchanged"

    return CompareResponse(
        baseline=run_summary(baseline),
        candidate=run_summary(candidate),
        same_scenario=baseline.scenario_name == candidate.scenario_name,
        same_scenario_hash=baseline.scenario_hash == candidate.scenario_hash,
        metrics=metrics,
        dimensions=dimensions,
        assertions=assertions,
        baseline_events=base_events,
        candidate_events=cand_events,
        regressions=regressions,
        improvements=improvements,
        verdict=overall,  # type: ignore[arg-type]
    )

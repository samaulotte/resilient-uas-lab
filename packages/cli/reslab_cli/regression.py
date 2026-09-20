"""Resilience regression check: compare candidate reports against baseline reports.

Reports are canonical `report.json` files (schema 1.0). Scenarios are matched by
scenario name. Thresholds come from a YAML file (see `regression-thresholds.yaml` at the
repository root for the documented format) or from built-in defaults.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "require_passed": True,
    "score_drop_max": 5.0,
    "metrics": {
        "recovery.mttr": {"increase_max": 2.0},
        "mission.completion": {"decrease_max": 0.05},
        "containment.flight_domain_affected": {"equals": False},
        "safety.loss_of_control": {"equals": False},
    },
}

LOWER_IS_BETTER = {
    "recovery.mttr",
    "recovery.max",
    "recovery.time_to_safe_state",
    "containment.affected_domains",
    "containment.propagation_depth",
    "containment.propagated_components",
    "time.degraded",
    "time.failed",
}


@dataclass
class Finding:
    scenario: str
    metric: str
    baseline: Any
    candidate: Any
    limit: str
    passed: bool
    message: str


@dataclass
class ScenarioResult:
    scenario: str
    passed: bool
    findings: list[Finding] = field(default_factory=list)
    note: str = ""


@dataclass
class RegressionOutcome:
    results: list[ScenarioResult]

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results) and bool(self.results)

    @property
    def failed_scenarios(self) -> list[ScenarioResult]:
        return [r for r in self.results if not r.passed]


def load_thresholds(path: Path | None) -> dict[str, Any]:
    if path is None:
        return json.loads(json.dumps(DEFAULT_THRESHOLDS))
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("thresholds file must be a mapping")
    merged = json.loads(json.dumps(DEFAULT_THRESHOLDS))
    merged.update({k: v for k, v in data.items() if k != "metrics"})
    merged["metrics"] = {**merged["metrics"], **(data.get("metrics") or {})}
    return merged


def load_reports(path: Path) -> dict[str, dict[str, Any]]:
    """Load one report or every `*.json` report under a directory, keyed by scenario name."""

    files = (
        [path]
        if path.is_file()
        else sorted(path.rglob("report.json")) or sorted(path.glob("*.json"))
    )
    reports: dict[str, dict[str, Any]] = {}
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{file}: not a JSON report ({exc})") from exc
        if not isinstance(data, dict) or "schema_version" not in data or "scenario" not in data:
            continue
        name = str(data["scenario"].get("name", file.stem))
        reports[name] = data
    if not reports:
        raise ValueError(f"no resilience report found under {path}")
    return reports


def _context(report: dict[str, Any]) -> dict[str, Any]:
    metrics = report.get("metrics", {})
    ctx: dict[str, Any] = {
        "score.total": report.get("resilience_score"),
        "recovery.mttr": metrics.get("recovery", {}).get("mean_time_to_recovery"),
        "recovery.max": metrics.get("recovery", {}).get("max_time_to_recovery"),
        "recovery.success_rate": metrics.get("recovery", {}).get("success_rate"),
        "recovery.time_to_safe_state": metrics.get("recovery", {}).get("time_to_safe_state"),
        "mission.completion": metrics.get("mission", {}).get("completion"),
        "mission.continuity": metrics.get("mission", {}).get("continuity"),
        "control.availability": metrics.get("availability", {}).get("control"),
        "navigation.integrity": metrics.get("availability", {}).get("navigation_integrity"),
        "communications.availability": metrics.get("availability", {}).get("communications"),
        "compute.availability": metrics.get("availability", {}).get("compute"),
        "containment.flight_domain_affected": metrics.get("propagation", {}).get(
            "flight_domain_affected"
        ),
        "containment.affected_domains": len(
            metrics.get("propagation", {}).get("affected_domains", [])
        ),
        "containment.propagation_depth": metrics.get("propagation", {}).get(
            "max_propagation_depth"
        ),
        "containment.propagated_components": len(
            metrics.get("propagation", {}).get("propagated_components", [])
        ),
        "safety.loss_of_control": metrics.get("safety", {}).get("loss_of_control"),
        "time.degraded": metrics.get("modes", {}).get("time_degraded"),
        "time.failed": metrics.get("modes", {}).get("time_failed"),
    }
    for key, value in metrics.get("recovery", {}).get("per_subsystem_max", {}).items():
        ctx[f"recovery.{key.replace('.', '_')}"] = value
    return ctx


def _fmt(value: Any, metric: str) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return str(value).lower()
    if metric in LOWER_IS_BETTER or (
        metric.startswith("recovery.") and metric != "recovery.success_rate"
    ):
        return f"{float(value):.1f} s"
    if metric == "score.total":
        return f"{float(value):.1f}"
    if isinstance(value, float) and 0 <= value <= 1:
        return f"{value * 100:.1f} %"
    return str(value)


def check_scenario(
    scenario: str,
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any],
    thresholds: dict[str, Any],
) -> ScenarioResult:
    result = ScenarioResult(scenario=scenario, passed=True)
    cand = _context(candidate)
    base = _context(baseline) if baseline else {}

    if thresholds.get("require_passed", True):
        outcome = candidate.get("result")
        passed = outcome == "passed"
        result.findings.append(
            Finding(
                scenario,
                "result",
                baseline.get("result") if baseline else None,
                outcome,
                "must be passed",
                passed,
                f"benchmark result {outcome}"
                + (f" ({candidate.get('score', {}).get('reason', '')})" if not passed else ""),
            )
        )
        result.passed &= passed

    drop_max = thresholds.get("score_drop_max")
    if (
        baseline
        and drop_max is not None
        and base.get("score.total") is not None
        and cand.get("score.total") is not None
    ):
        drop = float(base["score.total"]) - float(cand["score.total"])
        passed = drop <= float(drop_max)
        result.findings.append(
            Finding(
                scenario,
                "score.total",
                base["score.total"],
                cand["score.total"],
                f"drop <= {float(drop_max):.1f}",
                passed,
                f"score {base['score.total']:.1f} -> {cand['score.total']:.1f} (drop {drop:.1f})",
            )
        )
        result.passed &= passed

    for metric, rule in (thresholds.get("metrics") or {}).items():
        if not isinstance(rule, dict):
            continue
        value = cand.get(metric)
        ref = base.get(metric)
        if "equals" in rule:
            passed = value == rule["equals"]
            result.findings.append(
                Finding(
                    scenario,
                    metric,
                    ref,
                    value,
                    f"== {_fmt(rule['equals'], metric)}",
                    passed,
                    f"{metric} = {_fmt(value, metric)}, required {_fmt(rule['equals'], metric)}",
                )
            )
            result.passed &= passed
        if "max" in rule and value is not None:
            passed = float(value) <= float(rule["max"])
            result.findings.append(
                Finding(
                    scenario,
                    metric,
                    ref,
                    value,
                    f"<= {_fmt(float(rule['max']), metric)}",
                    passed,
                    f"{metric} = {_fmt(value, metric)}, maximum allowed "
                    f"{_fmt(float(rule['max']), metric)}",
                )
            )
            result.passed &= passed
        if "min" in rule and value is not None:
            passed = float(value) >= float(rule["min"])
            result.findings.append(
                Finding(
                    scenario,
                    metric,
                    ref,
                    value,
                    f">= {_fmt(float(rule['min']), metric)}",
                    passed,
                    f"{metric} = {_fmt(value, metric)}, minimum required "
                    f"{_fmt(float(rule['min']), metric)}",
                )
            )
            result.passed &= passed
        if baseline and ref is not None and value is not None and not isinstance(value, bool):
            if "increase_max" in rule:
                increase = float(value) - float(ref)
                passed = increase <= float(rule["increase_max"])
                result.findings.append(
                    Finding(
                        scenario,
                        metric,
                        ref,
                        value,
                        f"increase <= {_fmt(float(rule['increase_max']), metric)}",
                        passed,
                        f"{metric} {_fmt(ref, metric)} -> {_fmt(value, metric)} "
                        f"(maximum allowed increase {_fmt(float(rule['increase_max']), metric)})",
                    )
                )
                result.passed &= passed
            if "decrease_max" in rule:
                decrease = float(ref) - float(value)
                passed = decrease <= float(rule["decrease_max"])
                result.findings.append(
                    Finding(
                        scenario,
                        metric,
                        ref,
                        value,
                        f"decrease <= {_fmt(float(rule['decrease_max']), metric)}",
                        passed,
                        f"{metric} {_fmt(ref, metric)} -> {_fmt(value, metric)} "
                        f"(maximum allowed decrease {_fmt(float(rule['decrease_max']), metric)})",
                    )
                )
                result.passed &= passed
    if baseline is None:
        result.note = "no baseline report for this scenario; absolute thresholds only"
    return result


def run_regression(
    baseline_path: Path | None, candidate_path: Path, thresholds_path: Path | None
) -> RegressionOutcome:
    thresholds = load_thresholds(thresholds_path)
    candidates = load_reports(candidate_path)
    baselines = load_reports(baseline_path) if baseline_path else {}
    results = [
        check_scenario(name, baselines.get(name), report, thresholds)
        for name, report in sorted(candidates.items())
    ]
    return RegressionOutcome(results=results)


def render_text(outcome: RegressionOutcome) -> str:
    lines = ["Resilience Regression Check", ""]
    passed = sum(1 for r in outcome.results if r.passed)
    failed = len(outcome.results) - passed
    lines.append(f"{passed} scenario{'s' if passed != 1 else ''} passed")
    lines.append(f"{failed} scenario{'s' if failed != 1 else ''} failed")
    for result in outcome.results:
        if result.passed and not result.note:
            continue
        lines.append("")
        lines.append(f"Scenario: {result.scenario}")
        if result.note:
            lines.append(f"  Note: {result.note}")
        for finding in result.findings:
            if finding.passed and not result.passed:
                continue
            if finding.passed:
                continue
            lines.append(f"  {finding.message}")
            lines.append(f"  Limit: {finding.limit}")
        lines.append(f"  Result: {'PASSED' if result.passed else 'FAILED'}")
    lines.append("")
    lines.append(f"Result: {'PASSED' if outcome.passed else 'FAILED'}")
    return "\n".join(lines)


def render_json(outcome: RegressionOutcome) -> str:
    return json.dumps(
        {
            "passed": outcome.passed,
            "scenarios": [
                {
                    "scenario": r.scenario,
                    "passed": r.passed,
                    "note": r.note,
                    "findings": [f.__dict__ for f in r.findings],
                }
                for r in outcome.results
            ],
        },
        indent=2,
        default=str,
    )

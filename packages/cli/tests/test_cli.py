from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from reslab_cli import regression
from reslab_cli.main import app

SCENARIOS = Path(__file__).resolve().parents[3] / "scenarios"
runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "reslab 0.1.0" in result.output


def test_validate_all_starter_scenarios() -> None:
    result = runner.invoke(
        app, ["scenario", "validate", *map(str, sorted(SCENARIOS.glob("*.yaml")))]
    )
    assert result.exit_code == 0, result.output
    assert result.output.count("VALID") == 7


def test_validate_reports_errors(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        (SCENARIOS / "gnss-loss.yaml").read_text().replace("navigation.gnss", "navigation.nope")
    )
    result = runner.invoke(app, ["scenario", "validate", str(bad)])
    assert result.exit_code == 2
    assert "unknown subsystem" in result.output


def test_local_run_writes_report(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "run",
            str(SCENARIOS / "mission-compute-restart.yaml"),
            "--local",
            "--speed",
            "500",
            "-o",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "PASSED" in result.output
    reports = list(tmp_path.rglob("report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text())
    assert report["schema_version"] == "1.0"
    assert report["result"] == "passed"
    assert (reports[0].parent / "report.html").exists()
    assert (reports[0].parent / "mock-adapter.log").exists()


def test_local_run_rejects_non_mock_adapter(tmp_path: Path) -> None:
    text = (
        (SCENARIOS / "gnss-loss.yaml").read_text().replace("adapter: mock", "adapter: px4-gazebo")
    )
    path = tmp_path / "px4.yaml"
    path.write_text(text)
    result = runner.invoke(app, ["run", str(path), "--local", "-o", str(tmp_path)])
    assert result.exit_code != 0


def _report(
    scenario: str, *, score: float, mttr: float, result: str = "passed", completion: float = 1.0
) -> dict:
    return {
        "schema_version": "1.0",
        "scenario": {"name": scenario},
        "result": result,
        "resilience_score": score,
        "score": {"reason": "critical assertion violated" if result != "passed" else "ok"},
        "metrics": {
            "recovery": {
                "mean_time_to_recovery": mttr,
                "success_rate": 1.0,
                "per_subsystem_max": {},
            },
            "mission": {"completion": completion},
            "availability": {},
            "propagation": {
                "flight_domain_affected": False,
                "affected_domains": ["a"],
                "propagated_components": [],
            },
            "safety": {"loss_of_control": False},
            "modes": {"time_failed": 0.0},
        },
    }


def test_regression_detects_mttr_regression(tmp_path: Path) -> None:
    base = tmp_path / "baseline" / "mission-compute-restart"
    cand = tmp_path / "candidate" / "mission-compute-restart"
    base.mkdir(parents=True)
    cand.mkdir(parents=True)
    (base / "report.json").write_text(
        json.dumps(_report("mission-compute-restart", score=99.0, mttr=4.1))
    )
    (cand / "report.json").write_text(
        json.dumps(_report("mission-compute-restart", score=97.0, mttr=9.8))
    )
    thresholds = tmp_path / "thresholds.yaml"
    thresholds.write_text("metrics:\n  recovery.mttr:\n    max: 6.0\n    increase_max: 2.0\n")
    outcome = regression.run_regression(tmp_path / "baseline", tmp_path / "candidate", thresholds)
    assert not outcome.passed
    text = regression.render_text(outcome)
    assert "1 scenario failed" in text
    assert "Scenario: mission-compute-restart" in text
    assert "maximum allowed 6.0 s" in text
    assert "Result: FAILED" in text

    result = runner.invoke(
        app,
        [
            "regression",
            "check",
            "--candidate",
            str(tmp_path / "candidate"),
            "--baseline",
            str(tmp_path / "baseline"),
            "--thresholds",
            str(thresholds),
            "--json-output",
            str(tmp_path / "out.json"),
        ],
    )
    assert result.exit_code == 1
    data = json.loads((tmp_path / "out.json").read_text())
    assert data["passed"] is False


def test_regression_passes_and_requires_passed_result(tmp_path: Path) -> None:
    cand = tmp_path / "candidate"
    cand.mkdir()
    (cand / "a.json").write_text(json.dumps(_report("gnss-loss", score=98.0, mttr=0.1)))
    outcome = regression.run_regression(None, cand, None)
    assert outcome.passed
    assert "no baseline report" in outcome.results[0].note
    (cand / "b.json").write_text(
        json.dumps(_report("sensor-failure", score=70.0, mttr=1.0, result="failed"))
    )
    outcome = regression.run_regression(None, cand, None)
    assert not outcome.passed
    assert [r.scenario for r in outcome.failed_scenarios] == ["sensor-failure"]


def test_regression_rejects_missing_reports(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no resilience report"):
        regression.run_regression(None, tmp_path, None)

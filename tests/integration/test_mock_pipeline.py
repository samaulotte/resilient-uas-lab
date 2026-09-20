"""Complete scenario through the platform with the mock adapter (required in CI)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from integration_support import REPO_ROOT, wait_for_terminal

pytestmark = pytest.mark.integration

ARTIFACTS = REPO_ROOT / "artifacts" / "integration"


def test_platform_ready(client: httpx.Client) -> None:
    ready = client.get("/readyz").json()
    assert ready["status"] == "ready"
    assert ready["components"] == {"database": True, "bus": True, "artifact_store": True}


def test_scenario_library_seeded(client: httpx.Client) -> None:
    names = {s["name"] for s in client.get("/api/v1/scenarios").json()}
    assert {"compound-degradation", "gnss-loss", "em-transient-profile-a"} <= names


def test_invalid_scenario_never_starts(client: httpx.Client) -> None:
    response = client.post(
        "/api/v1/runs",
        json={"document": "apiVersion: resilient-uas.dev/v1alpha1\nkind: ResilienceScenario\n"},
    )
    assert response.status_code == 422
    failed = client.get("/api/v1/runs", params={"state": "FAILED"}).json()
    assert all(r["state"] == "FAILED" for r in failed["runs"])


def test_compound_scenario_end_to_end(client: httpx.Client) -> None:
    created = client.post(
        "/api/v1/runs",
        json={"scenario_name": "compound-degradation", "speed": 25, "label": "integration"},
    )
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]
    assert created.json()["state"] == "QUEUED"

    run = wait_for_terminal(client, run_id)
    assert run["state"] == "COMPLETED", run["reason"]
    assert run["result"] == "passed"
    assert run["mission_complete"] is True
    assert run["summary"]["fault_containment"] == "PASS"
    assert run["summary"]["safety_preservation"] == "PASS"
    assert run["summary"]["faults_injected"] == 3
    assert run["report_available"] is True
    assert run["provenance"]["scenario_hash"].startswith("sha256:")
    assert run["provenance"]["runner_id"]

    events = client.get(f"/api/v1/runs/{run_id}/events", params={"limit": 5000}).json()["events"]
    kinds = {e["kind"] for e in events}
    assert {
        "INJECTION_REQUEST",
        "INJECTION_APPLIED",
        "OBSERVED_EFFECT",
        "RECOVERY",
        "SYSTEM_RESPONSE",
    } <= kinds
    assert any(e["event_type"] == "local_autonomy_active" for e in events)

    telemetry = client.get(f"/api/v1/runs/{run_id}/telemetry", params={"limit": 200}).json()
    assert telemetry["total"] > 1000 and telemetry["count"] <= 200 and telemetry["stride"] > 1

    metrics = client.get(f"/api/v1/runs/{run_id}/metrics").json()
    assert metrics["context"]["containment.flight_domain_affected"] is False
    assert metrics["context"]["recovery.mission_compute"] < 10
    assert all(a["outcome"] == "passed" for a in metrics["assertions"])

    report = client.get(f"/api/v1/runs/{run_id}/report").json()
    assert report["schema_version"] == "1.0"
    assert report["result"] == "passed"
    assert report["metrics"]["events"]["applied"] == 3
    html = client.get(f"/api/v1/runs/{run_id}/report.html")
    assert html.status_code == 200 and "Resilience Report" in html.text

    artifact_names = {a["name"] for a in client.get(f"/api/v1/runs/{run_id}/artifacts").json()}
    assert {
        "report.json",
        "report.html",
        "events.json",
        "telemetry.jsonl.gz",
        "scenario.yaml",
    } <= artifact_names

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "report.json").write_text(json.dumps(report, indent=2))
    (ARTIFACTS / "report.html").write_text(html.text)
    Path(ARTIFACTS / "run.json").write_text(json.dumps(run, indent=2))


def test_replay_reproduces_analysis(client: httpx.Client) -> None:
    source = client.post(
        "/api/v1/runs", json={"scenario_name": "mission-compute-restart", "speed": 40, "seed": 3}
    ).json()
    source_run = wait_for_terminal(client, source["id"])
    assert source_run["state"] == "COMPLETED"
    replay = client.post(
        "/api/v1/runs",
        json={
            "scenario_name": "mission-compute-restart",
            "adapter": "replay",
            "replay_source_run_id": source["id"],
            "speed": 60,
        },
    )
    assert replay.status_code == 202, replay.text
    replay_run = wait_for_terminal(client, replay.json()["id"])
    assert replay_run["state"] == "COMPLETED", replay_run["reason"]
    assert replay_run["resilience_score"] == source_run["resilience_score"]
    compare = client.get(
        "/api/v1/compare", params={"baseline": source["id"], "candidate": replay.json()["id"]}
    ).json()
    assert compare["verdict"] == "unchanged"
    assert compare["same_scenario"] is True


def test_cancel_running_run(client: httpx.Client) -> None:
    created = client.post("/api/v1/runs", json={"scenario_name": "gnss-loss", "speed": 2}).json()
    deadline = time.time() + 60
    while time.time() < deadline:
        run = client.get(f"/api/v1/runs/{created['id']}").json()
        if run["state"] in ("RUNNING", "RECOVERING"):
            break
        time.sleep(0.5)
    response = client.post(f"/api/v1/runs/{created['id']}/cancel")
    assert response.status_code == 200
    run = wait_for_terminal(client, created["id"], timeout=60)
    assert run["state"] == "CANCELLED"
    assert run["result"] == "inconclusive"
    assert client.post(f"/api/v1/runs/{created['id']}/cancel").status_code == 409

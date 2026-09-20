"""Post-run analysis: metrics, assertions, scoring, report generation and artifact storage."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from reslab_core.analysis.scoring import DEFAULT_SCORE_PROFILE
from reslab_core.provenance import Provenance
from reslab_core.report import ReportArtifact, build_report, render_html_report
from reslab_core.report.model import ResilienceReport
from reslab_core.scenario import load_scenario
from reslab_core.states import RunState
from reslab_core.telemetry import PlannedPath
from reslab_core.topology import DEFAULT_TOPOLOGY
from reslab_platform.artifacts import ArtifactStore
from reslab_platform.db import Run, repository
from reslab_platform.logging import get_logger

log = get_logger(__name__)

REPORT_JSON = "report.json"
REPORT_HTML = "report.html"
EVENTS_JSON = "events.json"
TELEMETRY_EXPORT = "telemetry.jsonl.gz"
SCENARIO_SNAPSHOT = "scenario.yaml"


async def store_artifact(
    session: AsyncSession,
    store: ArtifactStore,
    run_id: str,
    *,
    name: str,
    data: bytes,
    content_type: str,
    description: str = "",
) -> ReportArtifact:
    stored = await store.put(run_id, name, data, content_type)
    await repository.upsert_artifact(
        session,
        run_id,
        name=name,
        content_type=content_type,
        size_bytes=stored.size_bytes,
        storage_key=stored.key,
        sha256=stored.sha256,
        description=description,
    )
    return ReportArtifact(
        name=name,
        content_type=content_type,
        size_bytes=stored.size_bytes,
        storage_key=stored.key,
        description=description,
        sha256=stored.sha256,
    )


async def analyze_run(
    session: AsyncSession,
    store: ArtifactStore,
    run: Run,
    *,
    final_state: RunState,
    reason: str = "",
) -> ResilienceReport:
    """Compute metrics, evaluate assertions, score, render and store the report."""

    run_id = str(run.id)
    scenario = load_scenario(run.scenario_document)
    events = await repository.list_events(session, run_id, limit=100_000)
    samples = await repository.list_telemetry(session, run_id)
    topology = await repository.get_default_topology(session) or DEFAULT_TOPOLOGY
    profile = await repository.get_score_profile(session, scenario.scoring.profile)
    if profile is None:
        log.warning("analysis.profile_missing", profile=scenario.scoring.profile)
        profile = DEFAULT_SCORE_PROFILE

    provenance = (
        Provenance.model_validate(run.provenance)
        if run.provenance
        else Provenance(
            scenario_hash=run.scenario_hash,
            scenario_version=run.scenario_version,
            adapter=run.adapter,
            seed=run.seed,
            speed=run.speed,
        )
    )
    provenance = provenance.model_copy(
        update={
            "started_at": run.started_at,
            "ended_at": run.ended_at or datetime.now(tz=UTC),
            "runner_id": run.runner_id,
            "score_profile": profile.name,
        }
    )

    existing_artifacts = [
        ReportArtifact(
            name=a.name,
            content_type=a.content_type,
            size_bytes=a.size_bytes,
            storage_key=a.storage_key,
            description=a.description,
            sha256=a.sha256,
        )
        for a in await repository.list_artifacts(session, run_id)
    ]

    # Export raw data first so the report can list every artifact.
    exports: list[ReportArtifact] = []
    exports.append(
        await store_artifact(
            session,
            store,
            run_id,
            name=SCENARIO_SNAPSHOT,
            data=run.scenario_document.encode("utf-8"),
            content_type="application/yaml",
            description="Scenario document exactly as executed",
        )
    )
    exports.append(
        await store_artifact(
            session,
            store,
            run_id,
            name=EVENTS_JSON,
            data=json.dumps([e.model_dump(mode="json") for e in events]).encode("utf-8"),
            content_type="application/json",
            description="Normalized run events",
        )
    )
    telemetry_lines = "\n".join(s.model_dump_json() for s in samples).encode("utf-8")
    exports.append(
        await store_artifact(
            session,
            store,
            run_id,
            name=TELEMETRY_EXPORT,
            data=gzip.compress(telemetry_lines),
            content_type="application/gzip",
            description="Normalized telemetry samples (JSON lines, gzip)",
        )
    )

    planned_path = PlannedPath.model_validate(run.planned_path) if run.planned_path else None
    report = build_report(
        run_id=run_id,
        scenario=scenario,
        scenario_hash=run.scenario_hash,
        events=events,
        samples=samples,
        provenance=provenance,
        run_state=final_state,
        started_at=run.started_at,
        ended_at=run.ended_at,
        reason=reason,
        planned_path=planned_path,
        artifacts=[*existing_artifacts, *exports],
        score_profile=profile,
        topology=topology,
    )
    report_json = report.model_dump_json(indent=2).encode("utf-8")
    json_artifact = await store_artifact(
        session,
        store,
        run_id,
        name=REPORT_JSON,
        data=report_json,
        content_type="application/json",
        description="Canonical machine-readable resilience report",
    )
    html_artifact = await store_artifact(
        session,
        store,
        run_id,
        name=REPORT_HTML,
        data=render_html_report(report).encode("utf-8"),
        content_type="text/html; charset=utf-8",
        description="Standalone human-readable resilience report",
    )
    report = report.model_copy(
        update={"artifacts": [*report.artifacts, json_artifact, html_artifact]}
    )

    await repository.replace_analysis(
        session, run_id, metrics=report.metrics, assertions=report.assertions, score=report.score
    )
    run.result = report.result.value
    run.hard_gate_result = report.hard_gate_result.value
    run.resilience_score = report.resilience_score
    run.summary = report.summary.model_dump(mode="json")
    run.event_count = len(events)
    run.sample_count = len(samples)
    run.last_simulation_time = samples[-1].t if samples else run.last_simulation_time
    run.mission_complete = report.summary.mission_complete
    run.provenance = provenance.model_dump(mode="json")
    await session.flush()
    log.info(
        "analysis.completed",
        run_id=run_id,
        result=report.result.value,
        score=report.resilience_score,
        events=len(events),
        samples=len(samples),
    )
    return report

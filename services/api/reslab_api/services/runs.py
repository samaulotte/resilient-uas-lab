"""Run creation, cancellation and serialization."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from reslab_api.schemas import ArtifactOut, RunCreateRequest, RunDetail, RunSummary
from reslab_api.state import AppState
from reslab_core.ids import validate_run_id
from reslab_core.protocol import CancelRequest, RunJob
from reslab_core.provenance import Provenance
from reslab_core.report.model import ReportSummary
from reslab_core.scenario import (
    ScenarioValidationError,
    ValidationIssue,
    load_scenario,
    scenario_content_hash,
)
from reslab_core.states import BenchmarkResult, RunState
from reslab_core.telemetry import PlannedPath
from reslab_platform.bus import Subjects
from reslab_platform.db import Run, repository
from reslab_platform.logging import get_logger
from reslab_platform.provenance import environment_metadata, image_versions

log = get_logger(__name__)


class RunCreationError(ValueError):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def run_summary(run: Run) -> RunSummary:
    return RunSummary(
        id=str(run.id),
        scenario_name=run.scenario_name,
        scenario_version=run.scenario_version,
        scenario_hash=run.scenario_hash,
        adapter=run.adapter,
        vehicle=run.vehicle,
        label=run.label or "",
        state=RunState(run.state),
        reason=run.reason or "",
        seed=run.seed,
        speed=run.speed,
        runner_id=run.runner_id,
        result=BenchmarkResult(run.result) if run.result else None,
        hard_gate_result=BenchmarkResult(run.hard_gate_result) if run.hard_gate_result else None,
        resilience_score=run.resilience_score,
        summary=ReportSummary.model_validate(run.summary) if run.summary else None,
        event_count=run.event_count or 0,
        sample_count=run.sample_count or 0,
        last_simulation_time=run.last_simulation_time or 0.0,
        mission_complete=bool(run.mission_complete),
        created_at=run.created_at,
        started_at=run.started_at,
        ended_at=run.ended_at,
        updated_at=run.updated_at,
        replay_source_run_id=str(run.replay_source_run_id) if run.replay_source_run_id else None,
    )


async def run_detail(session: AsyncSession, run: Run) -> RunDetail:
    artifacts = await repository.list_artifacts(session, run.id)
    summary = run_summary(run)
    return RunDetail(
        **summary.model_dump(),
        scenario_document=run.scenario_document,
        planned_path=PlannedPath.model_validate(run.planned_path) if run.planned_path else None,
        provenance=dict(run.provenance or {}),
        artifacts=[
            ArtifactOut(
                name=a.name,
                content_type=a.content_type,
                size_bytes=a.size_bytes,
                storage_key=a.storage_key,
                sha256=a.sha256,
                description=a.description,
                url=f"/api/v1/runs/{run.id}/artifacts/{a.name}",
            )
            for a in artifacts
        ],
        report_available=any(a.name == "report.json" for a in artifacts),
    )


async def create_run(session: AsyncSession, state: AppState, request: RunCreateRequest) -> Run:
    """CREATED -> VALIDATING -> QUEUED, then publish the job. Invalid scenarios never start."""

    if not request.scenario_name and not request.document:
        raise RunCreationError("provide scenario_name or document")

    document: str
    scenario_id: uuid.UUID | None = None
    if request.document:
        document = request.document
    else:
        stored = await repository.get_scenario(session, request.scenario_name or "")
        if stored is None:
            raise RunCreationError(f"scenario '{request.scenario_name}' not found", 404)
        document = stored.document
        scenario_id = stored.id

    # Adapter override is applied to the document so the executed YAML is what we store.
    if request.adapter:
        try:
            scenario = load_scenario(document)
        except ScenarioValidationError as exc:
            raise RunCreationError(_issues_text(exc.issues), 422) from exc
        if scenario.target.adapter != request.adapter:
            from reslab_core.scenario import scenario_to_yaml

            overridden = scenario.model_copy(
                update={"target": scenario.target.model_copy(update={"adapter": request.adapter})}
            )
            document = scenario_to_yaml(overridden)

    run = Run(
        id=uuid.uuid4(),
        scenario_id=scenario_id,
        scenario_name=request.scenario_name or "inline",
        scenario_version="1",
        scenario_hash="pending",
        scenario_document=document,
        adapter=request.adapter or "mock",
        vehicle="x500",
        label=request.label,
        state=RunState.CREATED.value,
        seed=request.seed if request.seed is not None else 42,
        speed=request.speed if request.speed is not None else 1.0,
        provenance={},
    )
    await repository.create_run(session, run)
    await repository.transition_run(session, run, RunState.VALIDATING)

    try:
        scenario = load_scenario(document)
        content_hash = scenario_content_hash(document)
    except ScenarioValidationError as exc:
        await repository.transition_run(
            session, run, RunState.FAILED, reason="invalid scenario: " + _issues_text(exc.issues)
        )
        raise RunCreationError(_issues_text(exc.issues), 422) from exc

    if scenario.target.adapter == "replay" and not request.replay_source_run_id:
        await repository.transition_run(
            session, run, RunState.FAILED, reason="replay adapter requires replay_source_run_id"
        )
        raise RunCreationError("replay adapter requires replay_source_run_id", 422)
    if request.replay_source_run_id:
        validate_run_id(request.replay_source_run_id)
        source = await repository.get_run(session, request.replay_source_run_id)
        if source is None or RunState(source.state) is not RunState.COMPLETED:
            await repository.transition_run(
                session, run, RunState.FAILED, reason="replay source run not found or not completed"
            )
            raise RunCreationError("replay source run not found or not completed", 422)
        run.replay_source_run_id = source.id

    seed = request.seed if request.seed is not None else scenario.simulation.seed
    speed = request.speed if request.speed is not None else scenario.simulation.speed
    provenance = Provenance(
        scenario_hash=content_hash,
        scenario_version=scenario.metadata.version,
        adapter=scenario.target.adapter,
        target_configuration=dict(scenario.target.configuration),
        seed=seed,
        speed=speed,
        git_commit=state.settings.git_commit,
        image_versions=image_versions(state.settings, component="api"),
        environment=environment_metadata(state.settings),
        score_profile=scenario.scoring.profile,
        data_origin="replay" if scenario.target.adapter == "replay" else "simulation",
    )
    run.scenario_name = scenario.metadata.name
    run.scenario_version = scenario.metadata.version
    run.scenario_hash = content_hash
    run.adapter = scenario.target.adapter
    run.vehicle = scenario.target.vehicle
    run.seed = seed
    run.speed = speed
    run.provenance = provenance.model_dump(mode="json")
    await repository.transition_run(session, run, RunState.QUEUED, reason="queued for a runner")
    await session.commit()

    job = RunJob(
        run_id=str(run.id),
        scenario_yaml=document,
        scenario_hash=content_hash,
        adapter=scenario.target.adapter,
        seed=seed,
        speed=speed,
        replay_source_run_id=request.replay_source_run_id,
    )
    try:
        await state.bus.publish_js(Subjects.JOBS_RUN, job)
    except Exception as exc:
        log.error("run.publish_failed", run_id=str(run.id), error=str(exc))
        await repository.transition_run(
            session, run, RunState.FAILED, reason="event bus unavailable: job not published"
        )
        await session.commit()
        raise RunCreationError("event bus unavailable, run could not be queued", 503) from exc
    await session.refresh(run)
    log.info("run.queued", run_id=str(run.id), scenario=run.scenario_name, adapter=run.adapter)
    return run


async def cancel_run(session: AsyncSession, state: AppState, run: Run, reason: str) -> bool:
    current = RunState(run.state)
    if current.is_terminal:
        raise RunCreationError(f"run is already {current.value.lower()}", 409)
    delivered = False
    if current in (RunState.CREATED, RunState.VALIDATING, RunState.QUEUED):
        await repository.transition_run(session, run, RunState.CANCELLED, reason=reason)
        run.ended_at = datetime.now(tz=UTC)
        await session.commit()
        await session.refresh(run)
    try:
        await state.bus.publish_core(
            Subjects.control_cancel(str(run.id)), CancelRequest(run_id=str(run.id), reason=reason)
        )
        delivered = True
    except Exception as exc:
        log.warning("run.cancel_publish_failed", run_id=str(run.id), error=str(exc))
    return delivered


def _issues_text(issues: list[ValidationIssue]) -> str:
    return "; ".join(f"{i.path}: {i.message}" for i in issues[:5])

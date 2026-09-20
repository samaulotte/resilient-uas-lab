from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from reslab_api.schemas import (
    ApiError,
    ArtifactOut,
    CancelResponse,
    EventsResponse,
    MetricsResponse,
    RecordingOut,
    RunCreateRequest,
    RunDetail,
    RunListResponse,
    TelemetryResponse,
)
from reslab_api.services.runs import (
    RunCreationError,
    cancel_run,
    create_run,
    run_detail,
    run_summary,
)
from reslab_api.state import AppState, get_session, get_state
from reslab_core.analysis.assertions import AssertionResult
from reslab_core.analysis.metrics import MetricsResult
from reslab_core.analysis.scoring import ScoreResult
from reslab_core.ids import InvalidIdentifierError, validate_artifact_name, validate_run_id
from reslab_core.report.model import ResilienceReport
from reslab_core.states import RunState
from reslab_platform.db import Run, repository

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])

# Reports are self-contained documents; stored content must never execute scripts.
REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"


async def _load_run(session: AsyncSession, run_id: str) -> Run:
    try:
        validate_run_id(run_id)
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    run = await repository.get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run '{run_id}' not found")
    return run


@router.get("", response_model=RunListResponse, summary="List runs (newest first)")
async def list_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    scenario: str | None = Query(default=None, max_length=64),
    state: RunState | None = None,
    adapter: str | None = Query(default=None, max_length=32),
    result: str | None = Query(default=None, max_length=16),
    session: AsyncSession = Depends(get_session),
) -> RunListResponse:
    runs, total = await repository.list_runs(
        session,
        limit=limit,
        offset=offset,
        scenario=scenario,
        state=state.value if state else None,
        adapter=adapter,
        result=result,
    )
    return RunListResponse(
        runs=[run_summary(r) for r in runs], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=RunDetail, status_code=202, summary="Create and queue a run")
async def create(
    payload: RunCreateRequest,
    state: AppState = Depends(get_state),
    session: AsyncSession = Depends(get_session),
) -> RunDetail:
    try:
        run = await create_run(session, state, payload)
    except RunCreationError as exc:
        await session.commit()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return await run_detail(session, run)


@router.get("/{run_id}", response_model=RunDetail, summary="Get a run")
async def get_run(run_id: str, session: AsyncSession = Depends(get_session)) -> RunDetail:
    run = await _load_run(session, run_id)
    return await run_detail(session, run)


@router.post("/{run_id}/cancel", response_model=CancelResponse, summary="Cancel a run")
async def cancel(
    run_id: str,
    state: AppState = Depends(get_state),
    session: AsyncSession = Depends(get_session),
) -> CancelResponse:
    run = await _load_run(session, run_id)
    try:
        delivered = await cancel_run(session, state, run, reason="cancelled by user")
    except RunCreationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return CancelResponse(run=run_summary(run), delivered=delivered)


@router.get("/{run_id}/events", response_model=EventsResponse, summary="Run events")
async def events(
    run_id: str,
    after_sequence: int = Query(default=-1, ge=-1),
    limit: int = Query(default=1000, ge=1, le=5000),
    kind: list[str] | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> EventsResponse:
    await _load_run(session, run_id)
    rows = await repository.list_events(
        session, run_id, after_sequence=after_sequence, limit=limit, kinds=kind
    )
    return EventsResponse(
        run_id=run_id,
        events=rows,
        count=len(rows),
        next_after_sequence=rows[-1].sequence if len(rows) == limit else None,
    )


@router.get("/{run_id}/telemetry", response_model=TelemetryResponse, summary="Run telemetry")
async def telemetry(
    run_id: str,
    t_from: float | None = Query(default=None, ge=0, alias="from"),
    t_to: float | None = Query(default=None, ge=0, alias="to"),
    limit: int | None = Query(default=None, ge=1),
    all: bool = Query(default=False, description="Return every sample (bounded by a hard cap)"),
    state: AppState = Depends(get_state),
    session: AsyncSession = Depends(get_session),
) -> TelemetryResponse:
    run = await _load_run(session, run_id)
    total, _ = await repository.telemetry_stats(session, run_id)
    hard_cap = 200_000
    page_max = state.settings.api_telemetry_page_max
    if all:
        stride = 1
        cap = hard_cap
    else:
        cap = min(limit or page_max, page_max)
        stride = max(1, -(-total // cap)) if total > cap else 1
    samples = await repository.list_telemetry(
        session, run_id, t_from=t_from, t_to=t_to, stride=stride, limit=cap
    )
    return TelemetryResponse(
        run_id=str(run.id),
        samples=samples,
        count=len(samples),
        total=total,
        stride=stride,
        complete=RunState(run.state).is_terminal,
    )


@router.get("/{run_id}/metrics", response_model=MetricsResponse, summary="Metrics and score")
async def metrics(run_id: str, session: AsyncSession = Depends(get_session)) -> MetricsResponse:
    await _load_run(session, run_id)
    row = await repository.get_metrics(session, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="metrics not available yet")
    assertions = [
        AssertionResult(
            expression=a.expression,
            severity=a.severity,  # type: ignore[arg-type]
            description=a.description,
            outcome=a.outcome,  # type: ignore[arg-type]
            measured=(a.measured or {}).get("value"),
            expected=a.expected.get("value"),
            operator=a.operator,
            metric_path=a.metric_path,
            explanation=a.explanation,
        )
        for a in await repository.list_assertions(session, run_id)
    ]
    return MetricsResponse(
        run_id=run_id,
        metrics=MetricsResult.model_validate(row.data),
        context=row.context,
        score=ScoreResult.model_validate(row.score),
        assertions=assertions,
    )


NOT_READY = {404: {"model": ApiError, "description": "Run not found or not analyzed yet"}}


@router.get(
    "/{run_id}/report",
    summary="Canonical JSON report",
    response_model=ResilienceReport,
    responses={
        200: {
            "description": "The stored report.json artifact, byte for byte",
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/ResilienceReport"}}
            },
        },
        **NOT_READY,
    },
)
async def report(
    run_id: str,
    state: AppState = Depends(get_state),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await _load_run(session, run_id)
    if not await repository.get_artifact(session, run_id, "report.json"):
        raise HTTPException(status_code=404, detail="report not available yet")
    data = await state.store.get(run_id, "report.json")
    return Response(content=data, media_type="application/json")


@router.get(
    "/{run_id}/report.html",
    summary="Standalone HTML report",
    response_class=Response,
    responses={
        200: {
            "description": "Self-contained HTML report (inline styles only, no scripts)",
            "content": {"text/html": {"schema": {"type": "string"}}},
        },
        **NOT_READY,
    },
)
async def report_html(
    run_id: str,
    state: AppState = Depends(get_state),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await _load_run(session, run_id)
    if not await repository.get_artifact(session, run_id, "report.html"):
        raise HTTPException(status_code=404, detail="report not available yet")
    data = await state.store.get(run_id, "report.html")
    return Response(
        content=data,
        media_type="text/html; charset=utf-8",
        headers={"Content-Security-Policy": REPORT_CSP},
    )


@router.get("/{run_id}/artifacts", response_model=list[ArtifactOut], summary="List artifacts")
async def artifacts(run_id: str, session: AsyncSession = Depends(get_session)) -> list[ArtifactOut]:
    await _load_run(session, run_id)
    rows = await repository.list_artifacts(session, run_id)
    return [
        ArtifactOut(
            name=a.name,
            content_type=a.content_type,
            size_bytes=a.size_bytes,
            sha256=a.sha256,
            description=a.description,
            url=f"/api/v1/runs/{run_id}/artifacts/{a.name}",
        )
        for a in rows
    ]


@router.get(
    "/{run_id}/artifacts/{name}",
    summary="Download an artifact",
    response_class=Response,
    responses={
        200: {
            "description": "Artifact content with its stored media type",
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        },
        400: {"model": ApiError, "description": "Invalid artifact name"},
        404: {"model": ApiError, "description": "Run or artifact not found"},
    },
)
async def artifact(
    run_id: str,
    name: str,
    state: AppState = Depends(get_state),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await _load_run(session, run_id)
    try:
        validate_artifact_name(name)
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = await repository.get_artifact(session, run_id, name)
    if row is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    data = await state.store.get(run_id, name)
    media_type = row.content_type
    if media_type.startswith("text/html"):
        # Reports are self-contained; never let stored content run scripts.
        headers = {"Content-Security-Policy": REPORT_CSP}
    else:
        headers = {"Content-Disposition": f'attachment; filename="{name}"'}
    return Response(content=data, media_type=media_type, headers=headers)


@router.get(
    "/{run_id}/recording",
    summary="Replay recording (normalized telemetry and events)",
    response_model=RecordingOut,
    responses={
        200: {
            "description": "Recording document served as an attachment",
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/RecordingOut"}}
            },
        },
        404: {"model": ApiError, "description": "Run not found"},
    },
)
async def recording(
    run_id: str,
    session: AsyncSession = Depends(get_session),
) -> Response:
    run = await _load_run(session, run_id)
    samples = await repository.list_telemetry(session, run_id)
    events_ = await repository.list_events(session, run_id, limit=100_000)
    payload = {
        "format_version": "1",
        "source_run_id": str(run.id),
        "source_adapter": run.adapter,
        "scenario_name": run.scenario_name,
        "planned_path": run.planned_path,
        "samples": [s.model_dump(mode="json") for s in samples],
        "events": [e.model_dump(mode="json") for e in events_],
    }
    return Response(
        content=json.dumps(payload),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="recording-{run_id}.json"'},
    )

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reslab_api.schemas import (
    ScenarioCreateRequest,
    ScenarioDetail,
    ScenarioSummary,
    ScenarioValidateRequest,
    ScenarioValidateResponse,
)
from reslab_api.services.runs import run_summary
from reslab_api.state import get_session
from reslab_core.ids import validate_slug
from reslab_core.scenario import (
    ScenarioValidationError,
    load_scenario,
    scenario_content_hash,
    scenario_to_yaml,
)
from reslab_core.scenario.loader import scenario_warnings
from reslab_platform.db import Run, Scenario, repository

router = APIRouter(prefix="/api/v1/scenarios", tags=["scenarios"])


async def _last_runs(session: AsyncSession, names: list[str]) -> dict[str, Run]:
    if not names:
        return {}
    result = await session.execute(
        select(Run).where(Run.scenario_name.in_(names)).order_by(Run.created_at.desc())
    )
    latest: dict[str, Run] = {}
    for run in result.scalars().all():
        latest.setdefault(run.scenario_name, run)
    return latest


def _summary(row: Scenario, last: Run | None) -> ScenarioSummary:
    return ScenarioSummary(
        name=row.name,
        description=row.description,
        version=row.version,
        adapter=row.adapter,
        tags=list(row.tags or []),
        content_hash=row.content_hash,
        event_count=row.event_count,
        assertion_count=row.assertion_count,
        source=row.source,
        updated_at=row.updated_at,
        last_run=run_summary(last) if last else None,
    )


@router.get("", response_model=list[ScenarioSummary], summary="List the scenario library")
async def list_scenarios(session: AsyncSession = Depends(get_session)) -> list[ScenarioSummary]:
    rows = await repository.list_scenarios(session)
    latest = await _last_runs(session, [r.name for r in rows])
    return [_summary(r, latest.get(r.name)) for r in rows]


@router.post(
    "/validate", response_model=ScenarioValidateResponse, summary="Validate a scenario document"
)
async def validate_scenario(payload: ScenarioValidateRequest) -> ScenarioValidateResponse:
    try:
        scenario = load_scenario(payload.document)
    except ScenarioValidationError as exc:
        return ScenarioValidateResponse(valid=False, issues=exc.issues, warnings=[])
    return ScenarioValidateResponse(
        valid=True,
        issues=[],
        warnings=scenario_warnings(scenario),
        scenario=scenario.model_dump(mode="json", by_alias=True),
        canonical_yaml=scenario_to_yaml(scenario),
        content_hash=scenario_content_hash(payload.document),
        expanded_events=[e.model_dump(mode="json") for e in scenario.expanded_events()],
    )


@router.post(
    "",
    response_model=ScenarioDetail,
    status_code=201,
    summary="Create or update a scenario in the library",
)
async def create_scenario(
    payload: ScenarioCreateRequest, session: AsyncSession = Depends(get_session)
) -> ScenarioDetail:
    try:
        scenario = load_scenario(payload.document)
    except ScenarioValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_scenario", "issues": [i.model_dump() for i in exc.issues]},
        ) from exc
    existing = await repository.get_scenario(session, scenario.metadata.name)
    if existing is not None and not payload.overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"scenario '{scenario.metadata.name}' already exists; set overwrite=true",
        )
    row = await repository.upsert_scenario(
        session,
        scenario,
        document=payload.document,
        content_hash=scenario_content_hash(payload.document),
        source="user",
    )
    return await _detail(session, row)


async def _detail(session: AsyncSession, row: Scenario) -> ScenarioDetail:
    scenario = load_scenario(row.document)
    latest = await _last_runs(session, [row.name])
    summary = _summary(row, latest.get(row.name))
    return ScenarioDetail(
        **summary.model_dump(),
        document=row.document,
        scenario=scenario.model_dump(mode="json", by_alias=True),
        expanded_events=[e.model_dump(mode="json") for e in scenario.expanded_events()],
        warnings=scenario_warnings(scenario),
    )


@router.get("/{name}", response_model=ScenarioDetail, summary="Get a scenario")
async def get_scenario(name: str, session: AsyncSession = Depends(get_session)) -> ScenarioDetail:
    validate_slug(name, what="scenario name")
    row = await repository.get_scenario(session, name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"scenario '{name}' not found")
    return await _detail(session, row)


@router.get("/{name}/document", summary="Get the raw YAML document", response_class=Response)
async def get_scenario_document(
    name: str, session: AsyncSession = Depends(get_session)
) -> Response:
    validate_slug(name, what="scenario name")
    row = await repository.get_scenario(session, name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"scenario '{name}' not found")
    return Response(content=row.document, media_type="application/yaml")


@router.delete("/{name}", status_code=204, summary="Delete a user scenario")
async def delete_scenario(name: str, session: AsyncSession = Depends(get_session)) -> Response:
    validate_slug(name, what="scenario name")
    row = await repository.get_scenario(session, name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"scenario '{name}' not found")
    if row.source == "library":
        raise HTTPException(status_code=409, detail="library scenarios cannot be deleted")
    await repository.delete_scenario(session, name)
    return Response(status_code=204)

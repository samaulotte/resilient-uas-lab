from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from reslab_api.schemas import CompareResponse
from reslab_api.services.compare import compare_runs
from reslab_api.state import get_session
from reslab_core.ids import InvalidIdentifierError, validate_run_id
from reslab_platform.db import repository

router = APIRouter(prefix="/api/v1", tags=["compare"])


@router.get("/compare", response_model=CompareResponse, summary="Compare two completed runs")
async def compare(
    baseline: str = Query(description="Baseline run id"),
    candidate: str = Query(description="Candidate run id"),
    session: AsyncSession = Depends(get_session),
) -> CompareResponse:
    try:
        validate_run_id(baseline)
        validate_run_id(candidate)
    except InvalidIdentifierError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    base = await repository.get_run(session, baseline)
    cand = await repository.get_run(session, candidate)
    if base is None or cand is None:
        raise HTTPException(status_code=404, detail="baseline or candidate run not found")
    return await compare_runs(session, base, cand)

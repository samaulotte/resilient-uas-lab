from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from reslab_api.state import AppState, get_state

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe (database, bus, artifact store)")
async def readyz(response: Response, state: AppState = Depends(get_state)) -> dict[str, object]:
    health = await state.health()
    ready = state.ready and health["database"]
    if not ready:
        response.status_code = 503
    return {"status": "ready" if ready else "degraded", "components": health}

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reslab_api.schemas import (
    AdapterOut,
    CatalogEntryOut,
    ComponentHealth,
    EffectDescriptor,
    ParameterSpecOut,
    RunnerOut,
    SystemInfo,
)
from reslab_api.state import AppState, get_session, get_state
from reslab_core.adapters_catalog import ADAPTER_CATALOG
from reslab_core.scenario.catalog import (
    DEFAULT_CATALOG,
    DURATION_REQUIRED_EFFECTS,
    EFFECT_PARAMETERS,
    TRANSIENT_EFFECTS,
    Effect,
)
from reslab_core.states import ComponentState, RunState
from reslab_core.topology import DEFAULT_TOPOLOGY
from reslab_core.versions import (
    PROTOCOL_VERSION,
    REPORT_SCHEMA_VERSION,
    SCENARIO_API_VERSION,
    SOFTWARE_VERSION,
)
from reslab_platform.db import Run, Scenario, repository

router = APIRouter(prefix="/api/v1", tags=["system"])

EFFECT_DESCRIPTIONS: dict[Effect, str] = {
    Effect.UNAVAILABLE: "The function is not provided at all until cleared.",
    Effect.INTERMITTENT: "The function alternates between available and unavailable.",
    Effect.DEGRADED: "The function is provided with reduced quality or capacity.",
    Effect.ERRONEOUS: "The function returns plausible but wrong output.",
    Effect.STUCK: "The output freezes at its last value.",
    Effect.RESTART: "The component restarts and recovers on its own.",
    Effect.CRASH: "The component fails; a watchdog restarts it later.",
    Effect.LATENCY: "Added delay on the communication path.",
    Effect.PACKET_LOSS: "A fraction of messages is dropped.",
    Effect.RESOURCE_PRESSURE: "CPU or memory pressure reduces processing capacity.",
    Effect.TEMPORARY_DISCONNECT: "The link disappears for a bounded duration.",
}


@router.get("/system", response_model=SystemInfo, summary="Platform, topology and catalog")
async def system_info(
    state: AppState = Depends(get_state), session: AsyncSession = Depends(get_session)
) -> SystemInfo:
    now = datetime.now(tz=UTC)
    stale = timedelta(seconds=state.settings.runner_stale_after_seconds)
    runners = await repository.list_runners(session)
    runner_out = [
        RunnerOut(
            runner_id=r.runner_id,
            adapters=list(r.adapters),
            version=r.version,
            active_run_id=str(r.active_run_id) if r.active_run_id else None,
            last_heartbeat_at=r.last_heartbeat_at,
            online=(now - r.last_heartbeat_at) <= stale,
        )
        for r in runners
    ]
    online_by_adapter: dict[str, list[str]] = {}
    for r in runner_out:
        if r.online:
            for adapter in r.adapters:
                online_by_adapter.setdefault(adapter, []).append(r.runner_id)
    adapters = [
        AdapterOut(
            **descriptor.model_dump(),
            online=bool(online_by_adapter.get(descriptor.name)),
            runners=online_by_adapter.get(descriptor.name, []),
        )
        for descriptor in ADAPTER_CATALOG
    ]
    topology = await repository.get_default_topology(session) or DEFAULT_TOPOLOGY
    catalog = [
        CatalogEntryOut(
            subsystem=e.component.id,
            name=e.component.name,
            domain=e.component.domain.value,
            category=e.component.category.value,
            trust_zone=e.component.trust_zone.value,
            healthy_state=e.component.healthy_state,
            critical=e.component.critical,
            description=e.component.description,
            effects=list(e.effects),
        )
        for e in DEFAULT_CATALOG.entries
    ]
    effects = [
        EffectDescriptor(
            effect=effect,
            transient=effect in TRANSIENT_EFFECTS,
            duration_required=effect in DURATION_REQUIRED_EFFECTS,
            parameters=[
                ParameterSpecOut(**p.model_dump()) for p in EFFECT_PARAMETERS.get(effect, ())
            ],
            description=EFFECT_DESCRIPTIONS.get(effect, ""),
        )
        for effect in Effect
    ]
    scenario_count = int(await session.scalar(select(func.count()).select_from(Scenario)) or 0)
    run_rows = await session.execute(select(Run.state, func.count()).group_by(Run.state))
    counts: dict[str, int] = {"scenarios": scenario_count, "runs": 0}
    for run_state, count in run_rows.all():
        counts["runs"] += int(count)
        counts[f"runs_{run_state.lower()}"] = int(count)
    health = await state.health()
    return SystemInfo(
        software_version=SOFTWARE_VERSION,
        scenario_api_version=SCENARIO_API_VERSION,
        report_schema_version=REPORT_SCHEMA_VERSION,
        protocol_version=PROTOCOL_VERSION,
        git_commit=state.settings.git_commit,
        environment=state.settings.environment,
        health=ComponentHealth(**health),
        topology=topology,
        catalog=catalog,
        effects=effects,
        adapters=adapters,
        runners=runner_out,
        score_profiles=await repository.list_score_profiles(session),
        counts=counts,
        component_states=list(ComponentState),
        run_states=list(RunState),
    )

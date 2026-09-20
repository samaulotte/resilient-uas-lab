"""Data access helpers shared by the API and the orchestrator."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from reslab_core.analysis.assertions import AssertionResult
from reslab_core.analysis.metrics import MetricsResult
from reslab_core.analysis.scoring import ScoreProfile, ScoreResult
from reslab_core.scenario.model import ResilienceScenario
from reslab_core.states import InvalidRunTransitionError, RunState, can_transition
from reslab_core.telemetry import RunEvent, TelemetrySample
from reslab_core.topology import SystemTopology
from reslab_platform.db.models import (
    Artifact,
    AssertionRow,
    MetricsRow,
    Run,
    RunEventRow,
    Runner,
    RunTelemetryChunk,
    Scenario,
    ScoreProfileRow,
    SystemComponent,
    SystemTopologyRow,
)


def _uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(value)


# --------------------------------------------------------------------------- scenarios


async def upsert_scenario(
    session: AsyncSession,
    scenario: ResilienceScenario,
    *,
    document: str,
    content_hash: str,
    source: str = "library",
) -> Scenario:
    values = {
        "name": scenario.metadata.name,
        "description": scenario.metadata.description,
        "version": scenario.metadata.version,
        "api_version": scenario.api_version,
        "content_hash": content_hash,
        "document": document,
        "adapter": scenario.target.adapter,
        "tags": list(scenario.metadata.tags),
        "source": source,
        "event_count": len(scenario.expanded_events()),
        "assertion_count": len(scenario.assertions),
    }
    statement = pg_insert(Scenario).values(id=uuid.uuid4(), **values)
    statement = statement.on_conflict_do_update(
        index_elements=[Scenario.name],
        set_={k: v for k, v in values.items() if k != "name"} | {"updated_at": func.now()},
    )
    await session.execute(statement)
    result = await session.execute(select(Scenario).where(Scenario.name == scenario.metadata.name))
    return result.scalar_one()


async def list_scenarios(session: AsyncSession) -> list[Scenario]:
    result = await session.execute(select(Scenario).order_by(Scenario.name))
    return list(result.scalars().all())


async def get_scenario(session: AsyncSession, name: str) -> Scenario | None:
    result = await session.execute(select(Scenario).where(Scenario.name == name))
    return result.scalar_one_or_none()


async def delete_scenario(session: AsyncSession, name: str) -> bool:
    result = await session.execute(delete(Scenario).where(Scenario.name == name))
    return bool(result.rowcount)


# --------------------------------------------------------------------------- runs


async def create_run(session: AsyncSession, run: Run) -> Run:
    session.add(run)
    await session.flush()
    return run


async def get_run(session: AsyncSession, run_id: str | uuid.UUID) -> Run | None:
    result = await session.execute(select(Run).where(Run.id == _uuid(run_id)))
    return result.scalar_one_or_none()


def _apply_run_filters(
    statement: Select[Any],
    *,
    scenario: str | None = None,
    state: str | None = None,
    adapter: str | None = None,
    result: str | None = None,
) -> Select[Any]:
    if scenario:
        statement = statement.where(Run.scenario_name == scenario)
    if state:
        statement = statement.where(Run.state == state)
    if adapter:
        statement = statement.where(Run.adapter == adapter)
    if result:
        statement = statement.where(Run.result == result)
    return statement


async def list_runs(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    scenario: str | None = None,
    state: str | None = None,
    adapter: str | None = None,
    result: str | None = None,
) -> tuple[list[Run], int]:
    base = _apply_run_filters(
        select(Run), scenario=scenario, state=state, adapter=adapter, result=result
    )
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.execute(base.order_by(Run.created_at.desc()).limit(limit).offset(offset))
    return list(rows.scalars().all()), int(total or 0)


async def list_active_runs(session: AsyncSession) -> list[Run]:
    active = [s.value for s in RunState if not s.is_terminal]
    result = await session.execute(select(Run).where(Run.state.in_(active)))
    return list(result.scalars().all())


async def transition_run(
    session: AsyncSession,
    run: Run,
    target: RunState,
    *,
    reason: str | None = None,
    **fields: Any,
) -> Run:
    """Apply a validated lifecycle transition. Raises on illegal transitions."""

    current = RunState(run.state)
    if current == target:
        for key, value in fields.items():
            setattr(run, key, value)
        return run
    if not can_transition(current, target):
        raise InvalidRunTransitionError(current, target)
    run.state = target.value
    if reason is not None:
        run.reason = reason
    now = datetime.now(tz=UTC)
    if target is RunState.RUNNING and run.started_at is None:
        run.started_at = now
    if target.is_terminal:
        run.ended_at = now
    for key, value in fields.items():
        setattr(run, key, value)
    await session.flush()
    return run


async def update_run_fields(session: AsyncSession, run_id: str | uuid.UUID, **fields: Any) -> None:
    await session.execute(update(Run).where(Run.id == _uuid(run_id)).values(**fields))


# --------------------------------------------------------------------------- events


def event_to_row(event: RunEvent) -> RunEventRow:
    return RunEventRow(
        run_id=_uuid(event.run_id),
        sequence=event.sequence,
        simulation_time=event.simulation_time,
        wall_time=event.wall_time,
        source=event.source.value,
        kind=event.kind.value,
        event_type=event.event_type,
        severity=event.severity.value,
        subsystem=event.subsystem,
        state_before=event.state_before.value if event.state_before else None,
        state_after=event.state_after.value if event.state_after else None,
        message=event.message,
        scenario_event_id=event.scenario_event_id,
        metadata_=event.metadata,
    )


def row_to_event(row: RunEventRow) -> RunEvent:
    return RunEvent(
        run_id=str(row.run_id),
        sequence=row.sequence,
        simulation_time=row.simulation_time,
        wall_time=row.wall_time,
        source=row.source,  # type: ignore[arg-type]
        kind=row.kind,  # type: ignore[arg-type]
        event_type=row.event_type,
        severity=row.severity,  # type: ignore[arg-type]
        subsystem=row.subsystem,
        state_before=row.state_before,  # type: ignore[arg-type]
        state_after=row.state_after,  # type: ignore[arg-type]
        message=row.message,
        scenario_event_id=row.scenario_event_id,
        metadata=dict(row.metadata_ or {}),
    )


async def insert_events(session: AsyncSession, events: Iterable[RunEvent]) -> int:
    rows = [event_to_row(e) for e in events]
    if not rows:
        return 0
    statement = pg_insert(RunEventRow).values(
        [
            {
                "run_id": r.run_id,
                "sequence": r.sequence,
                "simulation_time": r.simulation_time,
                "wall_time": r.wall_time,
                "source": r.source,
                "kind": r.kind,
                "event_type": r.event_type,
                "severity": r.severity,
                "subsystem": r.subsystem,
                "state_before": r.state_before,
                "state_after": r.state_after,
                "message": r.message,
                "scenario_event_id": r.scenario_event_id,
                "metadata_": r.metadata_,
            }
            for r in rows
        ]
    )
    statement = statement.on_conflict_do_nothing(constraint="uq_run_events_run_sequence")
    result = await session.execute(statement)
    return int(result.rowcount or 0)


async def list_events(
    session: AsyncSession,
    run_id: str | uuid.UUID,
    *,
    after_sequence: int = -1,
    limit: int = 1000,
    kinds: Sequence[str] | None = None,
) -> list[RunEvent]:
    statement = (
        select(RunEventRow)
        .where(RunEventRow.run_id == _uuid(run_id), RunEventRow.sequence > after_sequence)
        .order_by(RunEventRow.sequence)
        .limit(limit)
    )
    if kinds:
        statement = statement.where(RunEventRow.kind.in_(list(kinds)))
    result = await session.execute(statement)
    return [row_to_event(r) for r in result.scalars().all()]


async def count_events(session: AsyncSession, run_id: str | uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(RunEventRow).where(RunEventRow.run_id == _uuid(run_id))
        )
        or 0
    )


# --------------------------------------------------------------------------- telemetry


async def insert_telemetry_chunk(
    session: AsyncSession,
    run_id: str | uuid.UUID,
    sequence: int,
    samples: Sequence[TelemetrySample],
) -> bool:
    if not samples:
        return False
    statement = pg_insert(RunTelemetryChunk).values(
        run_id=_uuid(run_id),
        sequence=sequence,
        t_start=samples[0].t,
        t_end=samples[-1].t,
        sample_count=len(samples),
        samples=[s.model_dump(mode="json") for s in samples],
    )
    statement = statement.on_conflict_do_nothing(constraint="uq_run_telemetry_run_sequence")
    result = await session.execute(statement)
    return bool(result.rowcount)


async def list_telemetry(
    session: AsyncSession,
    run_id: str | uuid.UUID,
    *,
    t_from: float | None = None,
    t_to: float | None = None,
    stride: int = 1,
    limit: int | None = None,
) -> list[TelemetrySample]:
    statement = (
        select(RunTelemetryChunk)
        .where(RunTelemetryChunk.run_id == _uuid(run_id))
        .order_by(RunTelemetryChunk.sequence)
    )
    if t_from is not None:
        statement = statement.where(RunTelemetryChunk.t_end >= t_from)
    if t_to is not None:
        statement = statement.where(RunTelemetryChunk.t_start <= t_to)
    result = await session.execute(statement)
    samples: list[TelemetrySample] = []
    index = 0
    for chunk in result.scalars().all():
        for raw in chunk.samples:
            sample = TelemetrySample.model_validate(raw)
            if t_from is not None and sample.t < t_from:
                continue
            if t_to is not None and sample.t > t_to:
                continue
            if index % max(stride, 1) == 0:
                samples.append(sample)
                if limit is not None and len(samples) >= limit:
                    return samples
            index += 1
    return samples


async def telemetry_stats(session: AsyncSession, run_id: str | uuid.UUID) -> tuple[int, float]:
    result = await session.execute(
        select(
            func.coalesce(func.sum(RunTelemetryChunk.sample_count), 0),
            func.max(RunTelemetryChunk.t_end),
        ).where(RunTelemetryChunk.run_id == _uuid(run_id))
    )
    count, t_end = result.one()
    return int(count or 0), float(t_end or 0.0)


# --------------------------------------------------------------------------- analysis


async def replace_analysis(
    session: AsyncSession,
    run_id: str | uuid.UUID,
    *,
    metrics: MetricsResult,
    assertions: Sequence[AssertionResult],
    score: ScoreResult,
) -> None:
    rid = _uuid(run_id)
    await session.execute(delete(AssertionRow).where(AssertionRow.run_id == rid))
    await session.execute(delete(MetricsRow).where(MetricsRow.run_id == rid))
    session.add(
        MetricsRow(
            run_id=rid,
            data=metrics.model_dump(mode="json"),
            context=metrics.assertion_context(),
            score=score.model_dump(mode="json"),
        )
    )
    for position, a in enumerate(assertions):
        session.add(
            AssertionRow(
                run_id=rid,
                position=position,
                expression=a.expression,
                severity=a.severity.value,
                outcome=a.outcome.value,
                metric_path=a.metric_path,
                operator=a.operator,
                measured={"value": a.measured},
                expected={"value": a.expected},
                explanation=a.explanation,
                description=a.description,
            )
        )
    await session.flush()


async def get_metrics(session: AsyncSession, run_id: str | uuid.UUID) -> MetricsRow | None:
    result = await session.execute(select(MetricsRow).where(MetricsRow.run_id == _uuid(run_id)))
    return result.scalar_one_or_none()


async def list_assertions(session: AsyncSession, run_id: str | uuid.UUID) -> list[AssertionRow]:
    result = await session.execute(
        select(AssertionRow)
        .where(AssertionRow.run_id == _uuid(run_id))
        .order_by(AssertionRow.position)
    )
    return list(result.scalars().all())


# --------------------------------------------------------------------------- artifacts


async def upsert_artifact(
    session: AsyncSession,
    run_id: str | uuid.UUID,
    *,
    name: str,
    content_type: str,
    size_bytes: int,
    storage_key: str,
    sha256: str | None,
    description: str = "",
) -> None:
    values = {
        "run_id": _uuid(run_id),
        "name": name,
        "content_type": content_type,
        "size_bytes": size_bytes,
        "storage_key": storage_key,
        "sha256": sha256,
        "description": description,
    }
    statement = pg_insert(Artifact).values(id=uuid.uuid4(), **values)
    statement = statement.on_conflict_do_update(
        constraint="uq_artifacts_run_name",
        set_={k: v for k, v in values.items() if k not in ("run_id", "name")},
    )
    await session.execute(statement)


async def list_artifacts(session: AsyncSession, run_id: str | uuid.UUID) -> list[Artifact]:
    result = await session.execute(
        select(Artifact).where(Artifact.run_id == _uuid(run_id)).order_by(Artifact.name)
    )
    return list(result.scalars().all())


async def get_artifact(
    session: AsyncSession, run_id: str | uuid.UUID, name: str
) -> Artifact | None:
    result = await session.execute(
        select(Artifact).where(Artifact.run_id == _uuid(run_id), Artifact.name == name)
    )
    return result.scalar_one_or_none()


# --------------------------------------------------------------------------- runners


async def upsert_runner(
    session: AsyncSession,
    *,
    runner_id: str,
    adapters: Sequence[str],
    version: str,
    active_run_id: str | None,
    seen_at: datetime,
) -> None:
    values = {
        "adapters": list(adapters),
        "version": version,
        "active_run_id": _uuid(active_run_id) if active_run_id else None,
        "last_heartbeat_at": seen_at,
    }
    statement = pg_insert(Runner).values(runner_id=runner_id, **values)
    statement = statement.on_conflict_do_update(index_elements=[Runner.runner_id], set_=values)
    await session.execute(statement)


async def list_runners(session: AsyncSession) -> list[Runner]:
    result = await session.execute(select(Runner).order_by(Runner.runner_id))
    return list(result.scalars().all())


# --------------------------------------------------------------------------- topology / profiles


async def upsert_topology(
    session: AsyncSession, topology: SystemTopology, *, default: bool
) -> None:
    values = {
        "name": topology.name,
        "vehicle_class": topology.vehicle_class,
        "document": topology.model_dump(mode="json"),
        "is_default": default,
    }
    statement = pg_insert(SystemTopologyRow).values(id=topology.id, **values)
    statement = statement.on_conflict_do_update(index_elements=[SystemTopologyRow.id], set_=values)
    await session.execute(statement)
    for component in topology.components:
        cvalues = {
            "name": component.name,
            "domain": component.domain.value,
            "category": component.category.value,
            "trust_zone": component.trust_zone.value,
            "healthy_state": component.healthy_state.value,
            "critical": component.critical,
            "description": component.description,
        }
        cstatement = pg_insert(SystemComponent).values(
            topology_id=topology.id, component_id=component.id, **cvalues
        )
        cstatement = cstatement.on_conflict_do_update(
            constraint="uq_system_components_topology", set_=cvalues
        )
        await session.execute(cstatement)


async def get_default_topology(session: AsyncSession) -> SystemTopology | None:
    result = await session.execute(
        select(SystemTopologyRow).where(SystemTopologyRow.is_default.is_(True)).limit(1)
    )
    row = result.scalar_one_or_none()
    return SystemTopology.model_validate(row.document) if row else None


async def upsert_score_profile(
    session: AsyncSession, profile: ScoreProfile, *, default: bool
) -> None:
    values = {
        "description": profile.description,
        "weights": dict(profile.weights),
        "parameters": profile.parameters.model_dump(mode="json"),
        "is_default": default,
    }
    statement = pg_insert(ScoreProfileRow).values(name=profile.name, **values)
    statement = statement.on_conflict_do_update(index_elements=[ScoreProfileRow.name], set_=values)
    await session.execute(statement)


async def get_score_profile(session: AsyncSession, name: str) -> ScoreProfile | None:
    result = await session.execute(select(ScoreProfileRow).where(ScoreProfileRow.name == name))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return ScoreProfile(
        name=row.name, description=row.description, weights=row.weights, parameters=row.parameters
    )


async def list_score_profiles(session: AsyncSession) -> list[ScoreProfile]:
    result = await session.execute(select(ScoreProfileRow).order_by(ScoreProfileRow.name))
    return [
        ScoreProfile(
            name=r.name, description=r.description, weights=r.weights, parameters=r.parameters
        )
        for r in result.scalars().all()
    ]

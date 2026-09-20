"""Idempotent demo seeding: scenario library, default topology and score profile.

Seeding never fabricates runs. The optional completed demo run is produced by really
executing the compound scenario through the mock adapter (see `reslab_orchestrator`
`--seed-demo-run` and `scripts/seed_demo_run.py`).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from reslab_core.analysis.scoring import DEFAULT_SCORE_PROFILE
from reslab_core.scenario import ScenarioValidationError, load_scenario, scenario_content_hash
from reslab_core.topology import DEFAULT_TOPOLOGY
from reslab_platform.db import repository
from reslab_platform.logging import get_logger

log = get_logger(__name__)


async def seed_scenarios(session: AsyncSession, scenarios_dir: Path) -> int:
    count = 0
    if not scenarios_dir.exists():
        log.warning("seed.scenarios_dir_missing", path=str(scenarios_dir))
        return 0
    for path in sorted(scenarios_dir.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        try:
            scenario = load_scenario(text)
        except ScenarioValidationError as exc:
            log.error("seed.invalid_scenario", path=str(path), error=str(exc))
            continue
        await repository.upsert_scenario(
            session,
            scenario,
            document=text,
            content_hash=scenario_content_hash(text),
            source="library",
        )
        count += 1
    log.info("seed.scenarios", count=count)
    return count


async def seed_reference_data(session: AsyncSession) -> None:
    await repository.upsert_topology(session, DEFAULT_TOPOLOGY, default=True)
    await repository.upsert_score_profile(session, DEFAULT_SCORE_PROFILE, default=True)


async def seed_all(session: AsyncSession, scenarios_dir: Path) -> None:
    await seed_reference_data(session)
    await seed_scenarios(session, scenarios_dir)

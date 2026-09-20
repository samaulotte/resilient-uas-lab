"""`python -m reslab_platform.db.cli migrate|seed|migrate-and-seed`.

Used by the one-shot `migrate` Compose service. Waits for the database to accept
connections, applies migrations and seeds reference data idempotently.
"""

from __future__ import annotations

import asyncio
import sys
import time

from sqlalchemy import text

from reslab_platform.db.engine import create_engine, create_session_factory, session_scope
from reslab_platform.db.migrate import upgrade
from reslab_platform.logging import configure_logging, get_logger
from reslab_platform.seed import seed_all
from reslab_platform.settings import get_settings

log = get_logger(__name__)


async def wait_for_database(timeout: float = 120.0) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    deadline = time.monotonic() + timeout
    attempt = 0
    try:
        while True:
            attempt += 1
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                log.info("database.ready", attempts=attempt)
                return
            except Exception as exc:
                if time.monotonic() > deadline:
                    raise
                log.warning("database.waiting", attempt=attempt, error=type(exc).__name__)
                await asyncio.sleep(min(1.0 + attempt * 0.5, 5.0))
    finally:
        await engine.dispose()


async def seed() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with session_scope(factory) as session:
            await seed_all(session, settings.scenarios_dir)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format, service="migrate")
    args = argv if argv is not None else sys.argv[1:]
    command = args[0] if args else "migrate-and-seed"
    asyncio.run(wait_for_database())
    if command in ("migrate", "migrate-and-seed"):
        upgrade()
        log.info("database.migrated")
    if command in ("seed", "migrate-and-seed"):
        asyncio.run(seed())
        log.info("database.seeded")
    if command not in ("migrate", "seed", "migrate-and-seed"):
        log.error("unknown command", command=command)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

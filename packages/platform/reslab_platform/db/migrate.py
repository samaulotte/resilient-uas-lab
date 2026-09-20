"""Run database migrations programmatically (used by the `migrate` service and tests)."""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(ALEMBIC_INI))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade(database_url: str | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(database_url), revision)


def downgrade(database_url: str | None = None, revision: str = "base") -> None:
    command.downgrade(alembic_config(database_url), revision)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    revision = args[0] if args else "head"
    upgrade(revision=revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

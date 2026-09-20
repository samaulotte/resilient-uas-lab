"""Structured logging (JSON in containers, coloured console for local development).

Secrets are redacted by key name before rendering.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

SENSITIVE_KEYS = {"password", "secret", "token", "authorization", "access_key", "secret_key"}


def _redact(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict):
        lowered = key.lower()
        if any(marker in lowered for marker in SENSITIVE_KEYS):
            event_dict[key] = "***"
    return event_dict


def configure_logging(level: str = "INFO", fmt: str = "json", service: str = "reslab") -> None:
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )
    structlog.configure(
        processors=[*shared, structlog.processors.EventRenamer("message"), renderer]
        if fmt == "json"
        else [*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(sys.stderr),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=service)
    logging.basicConfig(level=level.upper(), stream=sys.stderr, format="%(message)s")
    for noisy in ("uvicorn.access", "botocore", "boto3", "urllib3", "alembic", "nats"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name) if name else structlog.get_logger()

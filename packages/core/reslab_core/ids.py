"""Identifier normalization and validation.

Every identifier that crosses a trust boundary (scenario file, API payload, artifact
name) is validated against a strict pattern before use. This is the first line of
defence against path traversal and injection through names.
"""

from __future__ import annotations

import re
import unicodedata
import uuid

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
SUBSYSTEM_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}\.[a-z][a-z0-9_]{0,31}$")
EVENT_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
ARTIFACT_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,127})$")
RUN_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class InvalidIdentifierError(ValueError):
    pass


def normalize_slug(value: str) -> str:
    """Normalize free text into a lowercase kebab-case slug."""

    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    text = text[:64].strip("-")
    if not text:
        raise InvalidIdentifierError(f"cannot derive a slug from {value!r}")
    return text


def validate_slug(value: str, *, what: str = "identifier") -> str:
    if not isinstance(value, str) or not SLUG_RE.match(value):
        raise InvalidIdentifierError(
            f"invalid {what} {value!r}: use lowercase letters, digits and dashes "
            "(max 64 characters)"
        )
    return value


def validate_subsystem_id(value: str) -> str:
    if not isinstance(value, str) or not SUBSYSTEM_RE.match(value):
        raise InvalidIdentifierError(
            f"invalid subsystem id {value!r}: expected '<category>.<component>' "
            "in lowercase snake_case, for example 'navigation.gnss'"
        )
    return value


def validate_artifact_name(value: str) -> str:
    """Validate an artifact file name: no path separators, no traversal, no hidden files."""

    if (
        not isinstance(value, str)
        or not ARTIFACT_NAME_RE.match(value)
        or ".." in value
        or "/" in value
        or "\\" in value
    ):
        raise InvalidIdentifierError(f"invalid artifact name {value!r}")
    return value


def validate_run_id(value: str) -> str:
    if not isinstance(value, str) or not RUN_ID_RE.match(value):
        raise InvalidIdentifierError(f"invalid run id {value!r}")
    return value


def new_run_id() -> str:
    return str(uuid.uuid4())

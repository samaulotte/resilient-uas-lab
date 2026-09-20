from __future__ import annotations

import pytest

from reslab_core.duration import DurationError, format_duration, format_mission_time, parse_duration
from reslab_core.ids import (
    InvalidIdentifierError,
    normalize_slug,
    validate_artifact_name,
    validate_run_id,
    validate_slug,
    validate_subsystem_id,
)


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("30s", 30.0),
        ("250ms", 0.25),
        ("1m", 60.0),
        ("1m30s", 90.0),
        ("4.5s", 4.5),
        ("1h2m3s", 3723.0),
    ],
)
def test_parse_duration(text: str, seconds: float) -> None:
    assert parse_duration(text) == pytest.approx(seconds)


@pytest.mark.parametrize("text", ["", "30", "s", "30 s", "1h1h", "abc", "-5s", "10sec"])
def test_parse_duration_rejects_invalid(text: str) -> None:
    with pytest.raises(DurationError):
        parse_duration(text)


def test_parse_duration_rejects_numbers() -> None:
    with pytest.raises(DurationError):
        parse_duration(30)  # type: ignore[arg-type]


def test_format_duration() -> None:
    assert format_duration(0.25) == "250ms"
    assert format_duration(4.2) == "4.2s"
    assert format_duration(65) == "1m05s"
    assert format_mission_time(64.9) == "T+01:04"


def test_slug_normalization() -> None:
    assert normalize_slug("Compound Degradation / Test") == "compound-degradation-test"
    assert validate_slug("gnss-loss") == "gnss-loss"
    with pytest.raises(InvalidIdentifierError):
        validate_slug("GNSS Loss")


def test_subsystem_id() -> None:
    assert validate_subsystem_id("navigation.gnss") == "navigation.gnss"
    for bad in ["navigation", "navigation.gnss.x", "Navigation.gnss", "nav gnss", "../etc"]:
        with pytest.raises(InvalidIdentifierError):
            validate_subsystem_id(bad)


@pytest.mark.parametrize("name", ["../report.json", "a/b", ".hidden", "a\\b", "", "x" * 200])
def test_artifact_name_rejects_traversal(name: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_artifact_name(name)


def test_artifact_name_accepts_plain_names() -> None:
    assert validate_artifact_name("report.json") == "report.json"
    assert validate_artifact_name("telemetry-2024.jsonl.gz") == "telemetry-2024.jsonl.gz"


def test_run_id() -> None:
    assert validate_run_id("00000000-0000-4000-8000-000000000001")
    with pytest.raises(InvalidIdentifierError):
        validate_run_id("not-a-uuid")

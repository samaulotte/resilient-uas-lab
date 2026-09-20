"""Parsing and formatting of human readable durations such as `30s`, `1m30s`, `250ms`.

Durations in scenario files are always strings with an explicit unit so that a bare
number can never be misread as seconds or milliseconds.
"""

from __future__ import annotations

import re

_DURATION_RE = re.compile(
    r"^(?:(?P<h>\d+)h)?(?:(?P<m>\d+)m(?!s))?(?:(?P<s>\d+(?:\.\d+)?)s)?(?:(?P<ms>\d+)ms)?$"
)


class DurationError(ValueError):
    pass


def parse_duration(value: str | int | float) -> float:
    """Parse a duration into seconds.

    Accepted forms: `250ms`, `30s`, `4.5s`, `2m`, `1m30s`, `1h`, `1h2m3s`.
    Numeric inputs are rejected on purpose; the unit has to be explicit.
    """

    if isinstance(value, bool) or not isinstance(value, str):
        raise DurationError(f"duration must be a string with a unit, got {value!r}")
    text = value.strip()
    if not text:
        raise DurationError("duration must not be empty")
    match = _DURATION_RE.match(text)
    if not match or not any(match.groupdict().values()):
        raise DurationError(
            f"invalid duration {value!r}; expected forms like '30s', '1m30s', '250ms'"
        )
    hours = int(match.group("h") or 0)
    minutes = int(match.group("m") or 0)
    seconds = float(match.group("s") or 0)
    millis = int(match.group("ms") or 0)
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def format_duration(seconds: float) -> str:
    """Format seconds as a compact duration string (`4.2s`, `1m05s`)."""

    if seconds < 0:
        return "-" + format_duration(-seconds)
    if seconds < 1:
        return f"{round(seconds * 1000)}ms"
    if seconds < 60:
        return f"{seconds:.1f}s".replace(".0s", "s")
    minutes, rem = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m{round(rem):02d}s"
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours}h{minutes:02d}m{round(rem):02d}s"


def format_mission_time(seconds: float) -> str:
    """Format simulation time as `T+MM:SS`."""

    sign = "-" if seconds < 0 else "+"
    total = int(abs(seconds))
    minutes, secs = divmod(total, 60)
    return f"T{sign}{minutes:02d}:{secs:02d}"

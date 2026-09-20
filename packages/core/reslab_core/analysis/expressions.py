"""Declarative assertion expressions.

Grammar (deliberately tiny, no code execution of any kind):

    expression := path operator literal
    path       := ident ("." ident)+
    operator   := "==" | "!=" | "<" | "<=" | ">" | ">="
    literal    := "true" | "false" | number | duration | percentage

Examples: `flight_control.available == true`, `recovery.mission_compute < 10s`,
`mission.completion >= 0.80`, `mission.completion >= 80%`.

Durations are normalized to seconds and percentages to ratios so that the same
metric can be compared with either notation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from reslab_core.duration import DurationError, parse_duration

_PATH_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_PERCENT_RE = re.compile(r"^-?\d+(?:\.\d+)?%$")
_TOKEN_RE = re.compile(r"^\s*(\S+)\s*(==|!=|<=|>=|<|>)\s*(\S+)\s*$")


class Operator(StrEnum):
    EQ = "=="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="


class ExpressionError(ValueError):
    pass


Literal = bool | float


@dataclass(frozen=True)
class Expression:
    path: str
    operator: Operator
    value: Literal
    raw_value: str

    @property
    def namespace(self) -> str:
        return self.path.split(".", 1)[0]

    def evaluate(self, measured: Literal | None) -> bool:
        if measured is None:
            return False
        if isinstance(self.value, bool) or isinstance(measured, bool):
            if not (isinstance(self.value, bool) and isinstance(measured, bool)):
                return False
            if self.operator is Operator.EQ:
                return measured is self.value
            if self.operator is Operator.NE:
                return measured is not self.value
            return False
        left = float(measured)
        right = float(self.value)
        match self.operator:
            case Operator.EQ:
                return abs(left - right) < 1e-9
            case Operator.NE:
                return abs(left - right) >= 1e-9
            case Operator.LT:
                return left < right
            case Operator.LE:
                return left <= right
            case Operator.GT:
                return left > right
            case Operator.GE:
                return left >= right
        return False  # pragma: no cover


def _parse_literal(text: str) -> Literal:
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if _NUMBER_RE.match(text):
        return float(text)
    if _PERCENT_RE.match(text):
        return float(text[:-1]) / 100.0
    try:
        return parse_duration(text)
    except DurationError:
        pass
    raise ExpressionError(
        f"invalid literal {text!r}; expected true/false, a number, a percentage or a duration"
    )


def parse_expression(text: str) -> Expression:
    if not isinstance(text, str) or len(text) > 200:
        raise ExpressionError("expression must be a string of at most 200 characters")
    match = _TOKEN_RE.match(text)
    if not match:
        raise ExpressionError(
            f"invalid expression {text!r}; expected '<metric.path> <operator> <value>'"
        )
    path, op, raw = match.groups()
    if not _PATH_RE.match(path):
        raise ExpressionError(
            f"invalid metric path {path!r}; use dotted lowercase identifiers such as "
            "'mission.completion'"
        )
    operator = Operator(op)
    value = _parse_literal(raw)
    if isinstance(value, bool) and operator not in (Operator.EQ, Operator.NE):
        raise ExpressionError("boolean values only support '==' and '!='")
    if path.split(".", 1)[0] not in KNOWN_NAMESPACES:
        raise ExpressionError(
            f"unknown metric namespace {path.split('.', 1)[0]!r}; known namespaces: "
            + ", ".join(sorted(KNOWN_NAMESPACES))
        )
    return Expression(path=path, operator=operator, value=value, raw_value=raw)


# Namespaces that the metrics engine can populate. Keys inside each namespace are
# documented in docs/metrics.md; `recovery.<subsystem>` accepts any subsystem id with
# the dot replaced by an underscore (recovery.mission_compute).
KNOWN_NAMESPACES: frozenset[str] = frozenset(
    {
        "flight_control",
        "safety",
        "recovery",
        "containment",
        "mission",
        "navigation",
        "communications",
        "compute",
        "control",
        "time",
        "events",
        "power",
    }
)

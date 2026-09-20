"""Strict scenario loading.

- YAML is parsed with `yaml.SafeLoader` only (no object construction, no tags).
- Documents are size-limited before parsing.
- Duplicate mapping keys are rejected.
- Only a single document is accepted.
- The parsed mapping is validated by the Pydantic schema with `extra="forbid"`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from reslab_core.scenario.errors import ScenarioValidationError, ValidationIssue
from reslab_core.scenario.model import ResilienceScenario

MAX_SCENARIO_BYTES = 256 * 1024


class _StrictSafeLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate keys and non-string keys."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[str] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"mapping keys must be strings, found {type(key).__name__}",
                    key_node.start_mark,
                )
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def parse_yaml_document(text: str) -> dict[str, Any]:
    if len(text.encode("utf-8")) > MAX_SCENARIO_BYTES:
        raise ScenarioValidationError(
            [
                ValidationIssue(
                    path="$",
                    message=f"scenario exceeds the {MAX_SCENARIO_BYTES // 1024} KiB size limit",
                    code="too_large",
                )
            ]
        )
    try:
        documents = list(yaml.load_all(text, Loader=_StrictSafeLoader))
    except yaml.YAMLError as exc:
        raise ScenarioValidationError(
            [ValidationIssue(path="$", message=f"YAML syntax error: {exc}", code="yaml")]
        ) from exc
    documents = [d for d in documents if d is not None]
    if len(documents) != 1:
        raise ScenarioValidationError(
            [
                ValidationIssue(
                    path="$",
                    message=f"expected exactly one YAML document, found {len(documents)}",
                    code="document_count",
                )
            ]
        )
    document = documents[0]
    if not isinstance(document, dict):
        raise ScenarioValidationError(
            [ValidationIssue(path="$", message="scenario must be a mapping", code="type")]
        )
    return document


def _issues_from_pydantic(exc: ValidationError) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for error in exc.errors(include_url=False):
        loc = error.get("loc", ())
        parts: list[str] = []
        for item in loc:
            if isinstance(item, int):
                parts[-1:] = [f"{parts[-1]}[{item}]"] if parts else [f"[{item}]"]
            else:
                parts.append(str(item))
        message = str(error.get("msg", "invalid value"))
        if message.startswith("Value error, "):
            message = message[len("Value error, ") :]
        issues.append(
            ValidationIssue(
                path=".".join(parts) or "$",
                message=message,
                code=str(error.get("type", "invalid")),
            )
        )
    return issues


def load_scenario(text: str) -> ResilienceScenario:
    """Parse and validate a scenario document. Raises `ScenarioValidationError`."""

    document = parse_yaml_document(text)
    try:
        return ResilienceScenario.model_validate(document)
    except ValidationError as exc:
        raise ScenarioValidationError(_issues_from_pydantic(exc)) from exc


def load_scenario_file(path: str | Path) -> ResilienceScenario:
    file_path = Path(path)
    if file_path.suffix not in {".yaml", ".yml"}:
        raise ScenarioValidationError(
            [ValidationIssue(path="$", message="scenario files must end with .yaml or .yml")]
        )
    if file_path.stat().st_size > MAX_SCENARIO_BYTES:
        raise ScenarioValidationError(
            [ValidationIssue(path="$", message="scenario file exceeds the size limit")]
        )
    return load_scenario(file_path.read_text(encoding="utf-8"))


def scenario_content_hash(text: str) -> str:
    """Stable content hash of the canonical scenario representation.

    Canonicalization goes through the validated model so that formatting differences
    (comments, key order, whitespace) do not change the hash while any semantic change
    does.
    """

    scenario = load_scenario(text)
    canonical = scenario.model_dump_json(by_alias=True, exclude_none=True)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def scenario_to_yaml(scenario: ResilienceScenario) -> str:
    data = scenario.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude_defaults=False
    )
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def scenario_warnings(scenario: ResilienceScenario) -> list[ValidationIssue]:
    """Non-blocking advisories for scenario authors."""

    from reslab_core.scenario.catalog import DEFAULT_CATALOG

    warnings: list[ValidationIssue] = []
    for index, event in enumerate(scenario.expanded_events()):
        entry = DEFAULT_CATALOG.entry(event.inject.subsystem)
        if entry is not None and entry.flight_critical_warning:
            warnings.append(
                ValidationIssue(
                    path=f"events[{index}].inject.subsystem",
                    message=(
                        f"'{event.inject.subsystem}' is flight-critical; the scenario "
                        "deliberately targets the protected domain"
                    ),
                    severity="warning",
                    code="flight_critical_target",
                )
            )
    if not scenario.critical_assertions():
        warnings.append(
            ValidationIssue(
                path="assertions",
                message="no critical assertion declared; the benchmark cannot hard-fail",
                severity="warning",
                code="no_critical_assertion",
            )
        )
    return warnings

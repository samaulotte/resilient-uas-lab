from __future__ import annotations

from pathlib import Path

import pytest

from reslab_core.scenario import (
    ScenarioValidationError,
    load_scenario,
    load_scenario_file,
    scenario_content_hash,
    scenario_to_yaml,
)
from reslab_core.scenario.loader import MAX_SCENARIO_BYTES, scenario_warnings
from reslab_core.states import ComponentState, Severity

MINIMAL = """
apiVersion: resilient-uas.dev/v1alpha1
kind: ResilienceScenario
metadata:
  name: minimal
target:
  adapter: mock
events:
  - id: gnss-loss
    at: 10s
    inject:
      subsystem: navigation.gnss
      effect: unavailable
assertions:
  - expression: flight_control.available == true
    severity: critical
"""


def test_all_starter_scenarios_load(scenarios_dir: Path) -> None:
    files = sorted(scenarios_dir.glob("*.yaml"))
    assert len(files) >= 7
    for path in files:
        scenario = load_scenario_file(path)
        assert scenario.metadata.name == path.stem
        assert scenario.expanded_events(), path


def test_minimal_scenario_defaults() -> None:
    scenario = load_scenario(MINIMAL)
    assert scenario.mission.timeout_seconds == 180.0
    assert scenario.recovery.gnss_loss == "dead_reckoning"
    assert scenario.simulation.seed == 42
    assert scenario.events[0].at_seconds == 10.0


def _expect_error(text: str, fragment: str) -> None:
    with pytest.raises(ScenarioValidationError) as info:
        load_scenario(text)
    messages = " | ".join(f"{i.path}: {i.message}" for i in info.value.issues)
    assert fragment in messages, messages


def test_unknown_subsystem_rejected() -> None:
    _expect_error(MINIMAL.replace("navigation.gnss", "navigation.unknown"), "unknown subsystem")


def test_disallowed_effect_rejected() -> None:
    _expect_error(MINIMAL.replace("effect: unavailable", "effect: crash"), "not allowed")


def test_unknown_effect_rejected() -> None:
    _expect_error(MINIMAL.replace("effect: unavailable", "effect: explode"), "effect")


def test_unknown_key_rejected() -> None:
    _expect_error(MINIMAL.replace("target:\n", "command: rm -rf /\ntarget:\n"), "command")


def test_duplicate_event_ids_rejected() -> None:
    text = (
        MINIMAL
        + """
  - id: gnss-loss
    at: 20s
    inject:
      subsystem: navigation.gnss
      effect: degraded
"""
    )
    text = text.replace("assertions:", "").replace(
        "  - expression: flight_control.available == true\n    severity: critical\n", ""
    )
    _expect_error(text, "duplicate event id")


def test_duration_on_transient_effect_rejected() -> None:
    text = MINIMAL.replace(
        "subsystem: navigation.gnss\n      effect: unavailable",
        "subsystem: mission.compute\n      effect: restart\n      duration: 5s",
    )
    _expect_error(text, "transient")


def test_event_after_timeout_rejected() -> None:
    _expect_error(MINIMAL.replace("at: 10s", "at: 500s"), "not before the mission timeout")


def test_bare_number_duration_rejected() -> None:
    _expect_error(MINIMAL.replace("at: 10s", "at: 10"), "at")


def test_invalid_assertion_rejected() -> None:
    _expect_error(
        MINIMAL.replace("flight_control.available == true", "import os; os.system('x')"),
        "expression",
    )


def test_unknown_metric_namespace_rejected() -> None:
    _expect_error(MINIMAL.replace("flight_control.available == true", "foo.bar == 1"), "namespace")


def test_unsupported_api_version_rejected() -> None:
    _expect_error(MINIMAL.replace("v1alpha1", "v9"), "unsupported apiVersion")


def test_yaml_tags_are_not_constructed() -> None:
    text = MINIMAL.replace("name: minimal", "name: !!python/object/apply:os.system ['id']")
    with pytest.raises(ScenarioValidationError):
        load_scenario(text)


def test_duplicate_keys_rejected() -> None:
    _expect_error(
        MINIMAL.replace("target:\n  adapter: mock", "target:\n  adapter: mock\n  adapter: mock"),
        "duplicate key",
    )


def test_multiple_documents_rejected() -> None:
    _expect_error(MINIMAL + "\n---\n" + MINIMAL, "exactly one YAML document")


def test_size_limit_enforced() -> None:
    padding = "#" + "x" * MAX_SCENARIO_BYTES
    _expect_error(MINIMAL + "\n" + padding, "size limit")


def test_parameters_validated_per_effect() -> None:
    text = MINIMAL.replace(
        "effect: unavailable", "effect: unavailable\n      parameters:\n        latency_ms: 100"
    )
    _expect_error(text, "not valid for effect")
    text = MINIMAL.replace(
        "effect: unavailable",
        "effect: intermittent\n      parameters:\n        duty_cycle: 4",
    )
    _expect_error(text, "<= 1.0")


def test_content_hash_is_semantic() -> None:
    a = scenario_content_hash(MINIMAL)
    reordered = MINIMAL.replace("kind: ResilienceScenario\n", "").replace(
        "apiVersion: resilient-uas.dev/v1alpha1",
        "kind: ResilienceScenario\napiVersion: resilient-uas.dev/v1alpha1",
    )
    assert scenario_content_hash(reordered + "\n# comment\n") == a
    assert scenario_content_hash(MINIMAL.replace("at: 10s", "at: 11s")) != a
    assert a.startswith("sha256:")


def test_round_trip_yaml() -> None:
    scenario = load_scenario(MINIMAL)
    text = scenario_to_yaml(scenario)
    again = load_scenario(text)
    assert again == scenario


def test_profile_expansion(scenarios_dir: Path) -> None:
    scenario = load_scenario_file(scenarios_dir / "em-transient-profile-a.yaml")
    events = scenario.expanded_events()
    subsystems = {e.inject.subsystem for e in events}
    assert subsystems == {"navigation.gnss", "mission.compute", "communications.telemetry"}
    restart = next(e for e in events if e.inject.subsystem == "mission.compute")
    assert restart.inject.duration is None
    gnss = next(e for e in events if e.inject.subsystem == "navigation.gnss")
    assert gnss.inject.duration == "8s"
    operational = [x for e in events for x in e.expect if x.state is ComponentState.OPERATIONAL]
    assert operational and operational[0].subsystem == "flight_control.core"


def test_warnings_for_flight_critical_targets() -> None:
    text = MINIMAL.replace(
        "subsystem: navigation.gnss\n      effect: unavailable",
        "subsystem: flight_control.core\n      effect: degraded",
    )
    scenario = load_scenario(text)
    codes = {w.code for w in scenario_warnings(scenario)}
    assert "flight_critical_target" in codes


def test_critical_assertions_listed() -> None:
    scenario = load_scenario(MINIMAL)
    assert [a.severity for a in scenario.critical_assertions()] == [Severity.CRITICAL]

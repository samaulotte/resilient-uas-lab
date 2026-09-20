from __future__ import annotations

from reslab_core.scenario.catalog import DEFAULT_CATALOG, Effect
from reslab_core.topology import CRITICAL_DOMAINS, DEFAULT_TOPOLOGY, Domain, TrustZone


def test_every_component_has_a_catalog_entry() -> None:
    ids = {e.component.id for e in DEFAULT_CATALOG.entries}
    assert ids == set(DEFAULT_TOPOLOGY.component_ids)


def test_dependencies_reference_known_components() -> None:
    for dep in DEFAULT_TOPOLOGY.dependencies:
        assert DEFAULT_TOPOLOGY.has_component(dep.provider), dep
        assert DEFAULT_TOPOLOGY.has_component(dep.dependent), dep


def test_trust_boundary_between_mission_and_flight() -> None:
    crossing = [d for d in DEFAULT_TOPOLOGY.dependencies if d.crosses_trust_boundary]
    assert crossing
    for dep in crossing:
        assert DEFAULT_TOPOLOGY.component(dep.provider).trust_zone is TrustZone.MISSION
        assert DEFAULT_TOPOLOGY.component(dep.dependent).trust_zone is TrustZone.FLIGHT_CRITICAL


def test_critical_components_live_in_critical_domains() -> None:
    for component_id in DEFAULT_TOPOLOGY.critical_component_ids:
        assert DEFAULT_TOPOLOGY.domain_of(component_id) in CRITICAL_DOMAINS


def test_propagation_depths() -> None:
    depths = DEFAULT_TOPOLOGY.propagation_depths(
        origins={"mission.compute"},
        affected={"mission.compute", "mission.planner", "network.companion_link", "power.bus"},
    )
    assert depths["mission.compute"] == 0
    assert depths["mission.planner"] == 1
    assert depths["network.companion_link"] == 2
    assert depths["power.bus"] == -1  # independent fault, not reachable from the origin


def test_catalog_forbids_destructive_effects_on_flight_core() -> None:
    entry = DEFAULT_CATALOG.entry("flight_control.core")
    assert entry is not None
    assert Effect.CRASH not in entry.effects
    assert Effect.UNAVAILABLE not in entry.effects
    assert entry.flight_critical_warning


def test_catalog_grouping_by_category() -> None:
    grouped = DEFAULT_CATALOG.by_category()
    assert len(grouped) >= 8
    assert all(entries for entries in grouped.values())
    assert DEFAULT_TOPOLOGY.domain_of("navigation.gnss") is Domain.NAVIGATION

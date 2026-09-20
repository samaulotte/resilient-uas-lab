from __future__ import annotations

import math

import pytest

from reslab_adapter_px4 import PX4_CAPABILITIES, PX4GazeboAdapter, mapping_for
from reslab_adapter_px4.mapping import FailureType, FailureUnit
from reslab_adapter_px4.transport import (
    GeodeticWaypoint,
    VehicleSnapshot,
    enu_to_geodetic,
    geodetic_to_enu,
)
from reslab_core.adapter import AdapterConfiguration, AdapterError, ClearRequest, InjectionRequest
from reslab_core.scenario.catalog import DEFAULT_CATALOG, Effect
from reslab_core.scenario.model import Mission, RecoveryPolicy, SimulationConfig, Target
from reslab_core.states import ComponentState, FlightMode, MissionPhase
from reslab_core.topology import DEFAULT_TOPOLOGY

RUN_ID = "00000000-0000-4000-8000-00000000000b"


class FakeLink:
    """In-memory PX4 link that records calls and lets tests drive the snapshot."""

    def __init__(self, url: str, *, fail_connect: bool = False) -> None:
        self.url = url
        self.fail_connect = fail_connect
        self.snap = VehicleSnapshot()
        self.params: dict[str, int] = {}
        self.mission: list[GeodeticWaypoint] = []
        self.rtl = False
        self.started = False
        self.injections: list[tuple[FailureUnit, FailureType]] = []
        self.reject: set[tuple[FailureUnit, FailureType]] = set()
        self.landed = False
        self.connect_calls = 0

    @property
    def version(self) -> str:
        return "fake"

    def snapshot(self) -> VehicleSnapshot:
        return self.snap

    async def connect(self, timeout: float) -> None:
        self.connect_calls += 1
        if self.fail_connect:
            raise TimeoutError("no heartbeat")
        self.snap.connected = True
        self.snap.home_latitude, self.snap.home_longitude, self.snap.home_altitude_msl = (
            47.397742,
            8.545594,
            488.0,
        )
        self.snap.latitude, self.snap.longitude, self.snap.altitude_msl = 47.397742, 8.545594, 488.0
        self.snap.health = {
            "local_position": True,
            "global_position": True,
            "mag": True,
            "gyro": True,
            "accel": True,
        }
        self.snap.gps_fix, self.snap.gps_satellites = "FIX_3D", 12
        self.snap.flight_mode = "READY"
        self.snap.battery_remaining, self.snap.battery_voltage = 0.95, 16.2

    async def disconnect(self) -> None:
        self.snap.connected = False

    async def set_param_int(self, name: str, value: int) -> None:
        self.params[name] = value

    async def upload_mission(self, waypoints: list[GeodeticWaypoint], rtl: bool) -> None:
        self.mission = list(waypoints)
        self.rtl = rtl
        self.snap.mission_total = len(waypoints)

    async def arm_and_start_mission(self) -> None:
        self.started = True
        self.snap.armed = True
        self.snap.in_air = True
        self.snap.flight_mode = "MISSION"

    async def inject_failure(self, unit: FailureUnit, failure_type: FailureType, instance: int = 0):
        if (unit, failure_type) in self.reject:
            return False, "unsupported"
        self.injections.append((unit, failure_type))
        if unit is FailureUnit.SENSOR_GPS:
            self.snap.gps_fix = "NO_FIX" if failure_type is FailureType.OFF else "FIX_3D"
            self.snap.health["global_position"] = failure_type is FailureType.OK
        return True, f"{unit.value} {failure_type.value}"

    async def land(self) -> None:
        self.landed = True


def _config() -> AdapterConfiguration:
    return AdapterConfiguration(
        run_id=RUN_ID,
        target=Target(adapter="px4-gazebo"),
        mission=Mission(timeout="120s"),
        recovery=RecoveryPolicy(),
        simulation=SimulationConfig(seed=1, speed=1.0, telemetry_rate_hz=50),
        topology=DEFAULT_TOPOLOGY,
    )


def test_mapping_is_a_subset_of_the_catalog() -> None:
    for subsystem, effects in PX4_CAPABILITIES.supported_effects.items():
        for effect in effects:
            assert DEFAULT_CATALOG.allows(subsystem, effect), (subsystem, effect)
            assert mapping_for(subsystem, effect) is not None
    assert (
        mapping_for("navigation.gnss", Effect.UNAVAILABLE).describe()
        == "px4:failure sensor_gps off"
    )
    assert mapping_for("mission.compute", Effect.RESTART).mechanism == "companion"
    assert mapping_for("security.gateway", Effect.UNAVAILABLE) is None


def test_geodetic_round_trip() -> None:
    lat, lon = enu_to_geodetic(150.0, -80.0, 47.397742, 8.545594)
    x, y = geodetic_to_enu(lat, lon, 47.397742, 8.545594)
    assert math.isclose(x, 150.0, abs_tol=0.01)
    assert math.isclose(y, -80.0, abs_tol=0.01)


async def test_prepare_uploads_mission_and_enables_failure_injection() -> None:
    links: list[FakeLink] = []

    def factory(url: str) -> FakeLink:
        link = FakeLink(url)
        links.append(link)
        return link

    clock = {"t": 0.0}
    adapter = PX4GazeboAdapter(
        connection_url="udpout://sim:14580", link_factory=factory, clock=lambda: clock["t"]
    )
    planned = await adapter.prepare(_config())
    link = links[0]
    assert link.params == {"SYS_FAILURE_EN": 1}
    assert len(link.mission) == len(planned.waypoints) >= 2
    assert link.rtl is True
    assert planned.origin is not None and math.isclose(planned.origin.latitude, 47.397742)

    await adapter.start()
    assert link.started
    clock["t"] += 1.0
    observation = adapter._observe_once()
    sample = observation.sample
    assert sample.source == "px4-gazebo"
    assert sample.flight.mode is FlightMode.MISSION
    assert sample.health["navigation.gnss"] is ComponentState.NOMINAL
    assert sample.health["mission.compute"] is ComponentState.OPERATIONAL
    assert sample.health["mission.planner"] is ComponentState.UNKNOWN
    assert sample.mission.phase is MissionPhase.ENROUTE

    result = await adapter.inject(
        InjectionRequest(
            scenario_event_id="gnss", subsystem="navigation.gnss", effect=Effect.UNAVAILABLE
        )
    )
    assert result.applied and result.mechanism == "px4:failure sensor_gps off"
    assert link.injections[-1] == (FailureUnit.SENSOR_GPS, FailureType.OFF)
    observation = adapter._observe_once()
    assert observation.sample.health["navigation.gnss"] is ComponentState.UNAVAILABLE
    assert observation.sample.health["navigation.estimator"] is ComponentState.DEGRADED
    assert any(c.subsystem == "navigation.gnss" for c in observation.state_changes)

    cleared = await adapter.clear(
        ClearRequest(
            scenario_event_id="gnss", subsystem="navigation.gnss", effect=Effect.UNAVAILABLE
        )
    )
    assert cleared.applied and link.injections[-1] == (FailureUnit.SENSOR_GPS, FailureType.OK)

    link.reject.add((FailureUnit.SENSOR_MAG, FailureType.WRONG))
    rejected = await adapter.inject(
        InjectionRequest(
            scenario_event_id="mag", subsystem="sensors.magnetometer", effect=Effect.ERRONEOUS
        )
    )
    assert not rejected.applied and "unsupported" in rejected.detail

    unsupported = await adapter.inject(
        InjectionRequest(
            scenario_event_id="gw", subsystem="security.gateway", effect=Effect.UNAVAILABLE
        )
    )
    assert not unsupported.applied

    # Companion restart drops the link and reconnects after the restart time.
    restart = await adapter.inject(
        InjectionRequest(
            scenario_event_id="restart",
            subsystem="mission.compute",
            effect=Effect.RESTART,
            parameters={"restart_time": "4s"},
        )
    )
    assert restart.applied and restart.mechanism == "companion:link_restart"
    assert not link.snap.connected
    observation = adapter._observe_once()
    assert observation.sample.health["mission.compute"] is ComponentState.RECOVERING
    assert observation.sample.health["communications.telemetry"] is ComponentState.UNAVAILABLE
    clock["t"] += 4.5
    await adapter._service_companion()
    assert link.snap.connected and link.connect_calls == 2
    observation = adapter._observe_once()
    assert observation.sample.health["mission.compute"] is ComponentState.RECOVERED

    link.snap.mission_current = link.snap.mission_total
    link.snap.mission_finished = True
    link.snap.armed = False
    link.snap.in_air = False
    observation = adapter._observe_once()
    assert observation.finished and observation.sample.mission.phase is MissionPhase.COMPLETE

    await adapter.stop()
    artifacts = await adapter.collect_artifacts()
    assert {a.name for a in artifacts} == {"px4-adapter.log", "px4-statustext.log"}


async def test_prepare_fails_clearly_when_simulator_is_unreachable() -> None:
    adapter = PX4GazeboAdapter(
        connection_url="udpout://nowhere:14580",
        connection_timeout=1.0,
        link_factory=lambda url: FakeLink(url, fail_connect=True),
    )
    with pytest.raises(AdapterError, match="could not connect to PX4"):
        await adapter.prepare(_config())

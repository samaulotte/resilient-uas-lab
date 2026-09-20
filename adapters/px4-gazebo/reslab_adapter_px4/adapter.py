"""`PX4GazeboAdapter`: the adapter contract over a MAVLink link to PX4 SITL."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import AsyncIterator, Callable

from reslab_adapter_px4.mapping import FailureType, mapping_for, supported_effects
from reslab_adapter_px4.transport import (
    GeodeticWaypoint,
    MavsdkLink,
    PX4Link,
    VehicleSnapshot,
    enu_to_geodetic,
    geodetic_to_enu,
)
from reslab_core.adapter import (
    AdapterCapabilities,
    AdapterConfiguration,
    AdapterError,
    AdapterKind,
    ArtifactBlob,
    AutonomousSystemAdapter,
    ClearRequest,
    HealthReport,
    InjectionRequest,
    InjectionResult,
    MissionEvent,
    Observation,
    Snapshot,
    SystemResponse,
)
from reslab_core.scenario.catalog import Effect
from reslab_core.states import ComponentState, FlightMode, MissionPhase
from reslab_core.telemetry import (
    Attitude,
    CommunicationsStatus,
    ComponentStateChange,
    FlightStatus,
    GeoPosition,
    MissionStatus,
    NavigationStatus,
    PlannedPath,
    Position,
    PowerStatus,
    TelemetrySample,
    Velocity,
    utcnow,
)
from reslab_core.topology import DEFAULT_TOPOLOGY, SystemTopology

PX4_ADAPTER_VERSION = "0.1.0"

PX4_CAPABILITIES = AdapterCapabilities(
    name="px4-gazebo",
    kind=AdapterKind.SIMULATION,
    description=(
        "PX4 SITL with Gazebo (headless). Effects are realised through PX4 System Failure "
        "Injection over MAVLink and companion-side link mechanisms; component states are "
        "derived from PX4 telemetry and health reports."
    ),
    vehicles=("x500", "gz_x500"),
    supported_effects=supported_effects(),
    deterministic=False,
    real_time_capable=True,
    data_origin="PX4 SITL simulation (software in the loop, no hardware)",
)

_MODE_MAP: dict[str, FlightMode] = {
    "TAKEOFF": FlightMode.TAKEOFF,
    "MISSION": FlightMode.MISSION,
    "HOLD": FlightMode.HOLD,
    "RETURN_TO_LAUNCH": FlightMode.RTL,
    "LAND": FlightMode.LAND,
    "READY": FlightMode.IDLE,
    "UNKNOWN": FlightMode.UNKNOWN,
}


class PX4GazeboAdapter(AutonomousSystemAdapter):
    def __init__(
        self,
        *,
        connection_url: str = "udpout://px4-sim:14580",
        connection_timeout: float = 120.0,
        link_factory: Callable[[str], PX4Link] | None = None,
        topology: SystemTopology = DEFAULT_TOPOLOGY,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.connection_url = connection_url
        self.connection_timeout = connection_timeout
        self._link_factory = link_factory or (lambda url: MavsdkLink(url))
        self.topology = topology
        self._clock = clock
        self._link: PX4Link | None = None
        self._configuration: AdapterConfiguration | None = None
        self._planned: PlannedPath | None = None
        self._home: tuple[float, float, float] | None = None
        self._t0: float | None = None
        self._states: dict[str, ComponentState] = {}
        self._active: dict[str, InjectionRequest] = {}
        self._companion_down_until: float | None = None
        self._companion_reason = ""
        self._previous_mode: FlightMode | None = None
        self._previous_status_count = 0
        self._log: list[str] = []
        self._stopped = False
        self._waypoints_total = 0

    @property
    def capabilities(self) -> AdapterCapabilities:
        return PX4_CAPABILITIES

    @property
    def version(self) -> str:
        return f"{PX4_ADAPTER_VERSION} ({self._link.version if self._link else 'not connected'})"

    # ------------------------------------------------------------------ lifecycle

    async def prepare(self, configuration: AdapterConfiguration) -> PlannedPath:
        self._configuration = configuration
        self._link = self._link_factory(self.connection_url)
        self._log.append(f"connecting to {self.connection_url}")
        try:
            await self._link.connect(self.connection_timeout)
        except Exception as exc:
            detail = str(exc) or type(exc).__name__
            raise AdapterError(
                f"could not connect to PX4 at {self.connection_url} within "
                f"{self.connection_timeout:.0f}s ({detail}). Is the simulation profile running "
                "(docker compose --profile sim up)?"
            ) from exc
        await self._link.set_param_int("SYS_FAILURE_EN", 1)
        home = await self._wait_for_home()
        self._home = home
        from reslab_adapter_mock.mission import planned_path_for

        planned = planned_path_for(configuration.mission).model_copy(
            update={
                "origin": GeoPosition(latitude=home[0], longitude=home[1], altitude_msl=home[2])
            }
        )
        waypoints = [
            GeodeticWaypoint(
                *enu_to_geodetic(wp.x, wp.y, home[0], home[1]),
                relative_altitude=wp.z,
                speed=configuration.mission.cruise_speed,
            )
            for wp in planned.waypoints
        ]
        await self._link.upload_mission(waypoints, rtl=True)
        self._waypoints_total = len(waypoints)
        self._planned = planned
        self._states = {c.id: ComponentState.UNKNOWN for c in self.topology.components}
        self._log.append(
            f"mission uploaded: {len(waypoints)} items, home {home[0]:.6f},{home[1]:.6f}"
        )
        return planned

    async def _wait_for_home(self) -> tuple[float, float, float]:
        assert self._link is not None
        deadline = self._clock() + self.connection_timeout
        while self._clock() < deadline:
            snap = self._link.snapshot()
            if snap.home_latitude is not None and snap.home_longitude is not None:
                return (snap.home_latitude, snap.home_longitude, snap.home_altitude_msl or 0.0)
            if (
                snap.latitude is not None
                and snap.longitude is not None
                and snap.health.get("global_position")
            ):
                return (snap.latitude, snap.longitude, snap.altitude_msl or 0.0)
            await asyncio.sleep(0.2)
        raise AdapterError("PX4 did not report a home position; GNSS lock not acquired")

    async def start(self) -> None:
        assert self._link is not None
        await self._link.arm_and_start_mission()
        self._t0 = self._clock()
        self._log.append("armed, mission started")

    async def inject(self, request: InjectionRequest) -> InjectionResult:
        mapping = mapping_for(request.subsystem, request.effect)
        if mapping is None:
            return InjectionResult(
                applied=False,
                mechanism="px4",
                detail=f"{request.subsystem}:{request.effect.value} has no PX4 mechanism",
            )
        if mapping.mechanism == "failure" and mapping.unit and mapping.failure_type:
            if self._link is None or not self._link.snapshot().connected:
                return InjectionResult(
                    applied=False, mechanism=mapping.describe(), detail="link down"
                )
            applied, detail = await self._link.inject_failure(mapping.unit, mapping.failure_type)
            if applied:
                self._active[request.scenario_event_id] = request
            self._log.append(f"inject {request.subsystem} {request.effect.value}: {detail}")
            return InjectionResult(applied=applied, mechanism=mapping.describe(), detail=detail)
        # companion mechanisms
        duration = self._companion_duration(request)
        self._companion_down_until = None if duration is None else self._clock() + duration
        self._companion_reason = mapping.companion_action or "companion"
        self._active[request.scenario_event_id] = request
        if self._link is not None:
            await self._link.disconnect()
        self._log.append(f"companion {mapping.companion_action}: link dropped")
        return InjectionResult(
            applied=True,
            mechanism=mapping.describe(),
            detail=mapping.note,
        )

    def _companion_duration(self, request: InjectionRequest) -> float | None:
        if request.effect is Effect.RESTART:
            value = request.parameters.get("restart_time")
            return _param_seconds(value, 5.0)
        if request.effect is Effect.CRASH:
            return _param_seconds(request.parameters.get("watchdog_time"), 2.0) + 5.0
        return request.duration  # unavailable: until cleared (None) or bounded

    async def clear(self, request: ClearRequest) -> InjectionResult:
        active = self._active.pop(request.scenario_event_id, None)
        mapping = mapping_for(request.subsystem, request.effect)
        if mapping is None or active is None:
            return InjectionResult(applied=False, mechanism="px4", detail="effect not active")
        if mapping.mechanism == "failure" and mapping.unit:
            if self._link is None or not self._link.snapshot().connected:
                return InjectionResult(
                    applied=False, mechanism=mapping.describe(), detail="link down"
                )
            applied, detail = await self._link.inject_failure(mapping.unit, FailureType.OK)
            return InjectionResult(applied=applied, mechanism=mapping.describe(), detail=detail)
        self._companion_down_until = self._clock()
        return InjectionResult(applied=True, mechanism=mapping.describe(), detail="link restored")

    async def observe(self) -> AsyncIterator[Observation]:
        assert self._configuration is not None
        rate = self._configuration.simulation.telemetry_rate_hz
        interval = 1.0 / rate
        while not self._stopped:
            await self._service_companion()
            observation = self._observe_once()
            yield observation
            if observation.finished:
                return
            await asyncio.sleep(interval)

    async def _service_companion(self) -> None:
        if self._companion_down_until is None:
            return
        if self._clock() >= self._companion_down_until:
            self._companion_down_until = None
            assert self._link is not None
            try:
                await self._link.connect(self.connection_timeout)
                self._log.append("companion link re-established")
            except Exception as exc:
                self._log.append(f"companion reconnect failed: {exc}")

    def _sim_time(self) -> float:
        return 0.0 if self._t0 is None else self._clock() - self._t0

    def _observe_once(self) -> Observation:
        assert self._link is not None and self._home is not None
        snap = self._link.snapshot()
        t = self._sim_time()
        states = self._derive_states(snap)
        changes = [
            ComponentStateChange(
                subsystem=subsystem,
                state_before=self._states.get(subsystem, ComponentState.UNKNOWN),
                state_after=state,
                reason="px4 telemetry",
            )
            for subsystem, state in states.items()
            if self._states.get(subsystem) != state
        ]
        self._states = states

        responses: list[SystemResponse] = []
        mode = (
            _MODE_MAP.get(snap.flight_mode, FlightMode.UNKNOWN)
            if snap.connected
            else FlightMode.UNKNOWN
        )
        if snap.connected and self._previous_mode is not None and mode != self._previous_mode:
            safe = mode in (FlightMode.HOLD, FlightMode.RTL, FlightMode.LAND)
            responses.append(
                SystemResponse(
                    response_type=f"mode_{mode.value.lower()}",
                    message=f"PX4 flight mode {self._previous_mode.value} -> {mode.value}",
                    subsystem="flight_control.core",
                    safe_state=safe and self._previous_mode is FlightMode.MISSION,
                )
            )
        if snap.connected:
            self._previous_mode = mode
        new_status = snap.status_texts[self._previous_status_count :]
        self._previous_status_count = len(snap.status_texts)
        for text in new_status:
            lowered = text.lower()
            if "failsafe" in lowered or "lost" in lowered or "critical" in lowered:
                responses.append(
                    SystemResponse(
                        response_type="px4_status",
                        message=text[:200],
                        subsystem="flight_control.core",
                        safe_state="failsafe" in lowered,
                    )
                )

        x, y = (0.0, 0.0)
        if snap.latitude is not None and snap.longitude is not None:
            x, y = geodetic_to_enu(snap.latitude, snap.longitude, self._home[0], self._home[1])
        z = snap.relative_altitude or 0.0
        progress = 0.0
        if snap.mission_total > 0:
            progress = min(1.0, snap.mission_current / snap.mission_total)
        finished = snap.connected and snap.mission_finished and not snap.armed and not snap.in_air
        if finished:
            phase = MissionPhase.COMPLETE
        elif mode is FlightMode.TAKEOFF:
            phase = MissionPhase.TAKEOFF
        elif mode is FlightMode.HOLD:
            phase = MissionPhase.HOLDING
        elif mode is FlightMode.RTL:
            phase = MissionPhase.RETURNING
        elif mode is FlightMode.LAND:
            phase = MissionPhase.LANDING
        elif self._t0 is None:
            phase = MissionPhase.PENDING
        else:
            phase = MissionPhase.ENROUTE
        mission_events: list[MissionEvent] = []
        if finished:
            mission_events.append(
                MissionEvent(
                    event_type="landed",
                    message="PX4 mission finished, vehicle landed",
                    progress=1.0,
                )
            )
        c2_down = any(
            r.subsystem in ("communications.c2", "external.gcs") for r in self._active.values()
        )
        sample = TelemetrySample(
            t=round(t, 3),
            wall_time=utcnow(),
            source="px4-gazebo",
            position=Position(x=round(x, 3), y=round(y, 3), z=round(z, 3)),
            geo=(
                GeoPosition(
                    latitude=snap.latitude,
                    longitude=snap.longitude,
                    altitude_msl=snap.altitude_msl or 0.0,
                )
                if snap.latitude is not None and snap.longitude is not None
                else None
            ),
            attitude=Attitude(roll=snap.roll, pitch=snap.pitch, yaw=snap.yaw),
            velocity=Velocity(vx=snap.ve, vy=snap.vn, vz=-snap.vd),
            mission=MissionStatus(
                phase=phase,
                progress=round(progress, 4),
                waypoint_index=snap.mission_current,
                waypoints_total=snap.mission_total or self._waypoints_total,
            ),
            flight=FlightStatus(
                mode=mode,
                armed=snap.armed,
                control_authority=snap.connected and mode is not FlightMode.UNKNOWN,
                autonomy="failsafe" if mode in (FlightMode.HOLD, FlightMode.RTL) else "mission",
            ),
            navigation=NavigationStatus(
                source="gnss" if snap.gps_fix not in ("NO_GPS", "NO_FIX") else "none",
                gnss_fix=snap.gps_fix not in ("NO_GPS", "NO_FIX"),
                position_error=0.0,
                satellites=snap.gps_satellites,
            ),
            communications=CommunicationsStatus(
                c2_link=snap.connected and not c2_down, telemetry_link=snap.connected
            ),
            power=PowerStatus(
                voltage=round(snap.battery_voltage, 2),
                remaining=max(0.0, min(1.0, snap.battery_remaining)),
            ),
            health=dict(states),
        )
        return Observation(
            sample=sample,
            state_changes=tuple(changes),
            responses=tuple(responses),
            mission_events=tuple(mission_events),
            finished=finished,
        )

    def _derive_states(self, snap: VehicleSnapshot) -> dict[str, ComponentState]:
        states = {c.id: ComponentState.UNKNOWN for c in self.topology.components}
        companion_down = self._companion_down_until is not None or not snap.connected
        if self._companion_down_until is not None:
            states["mission.compute"] = ComponentState.RECOVERING
        elif snap.connected:
            states["mission.compute"] = (
                ComponentState.RECOVERED
                if self._states.get("mission.compute") is ComponentState.RECOVERING
                else ComponentState.OPERATIONAL
            )
        if companion_down:
            states["communications.telemetry"] = ComponentState.UNAVAILABLE
            return states
        states["communications.telemetry"] = ComponentState.NOMINAL
        c2_injected = any(
            r.subsystem in ("communications.c2", "external.gcs") for r in self._active.values()
        )
        states["communications.c2"] = (
            ComponentState.UNAVAILABLE if c2_injected else ComponentState.NOMINAL
        )
        if snap.gps_fix in ("NO_GPS", "NO_FIX"):
            states["navigation.gnss"] = ComponentState.UNAVAILABLE
        elif snap.gps_fix == "FIX_2D" or snap.gps_satellites < 6:
            states["navigation.gnss"] = ComponentState.DEGRADED
        else:
            states["navigation.gnss"] = ComponentState.NOMINAL
        local_ok = snap.health.get("local_position", False)
        global_ok = snap.health.get("global_position", False)
        if local_ok and global_ok:
            states["navigation.estimator"] = ComponentState.NOMINAL
        elif local_ok:
            states["navigation.estimator"] = ComponentState.DEGRADED
        elif snap.health:
            states["navigation.estimator"] = ComponentState.UNAVAILABLE
        if snap.health:
            states["sensors.magnetometer"] = (
                ComponentState.NOMINAL if snap.health.get("mag") else ComponentState.DEGRADED
            )
            states["sensors.imu"] = (
                ComponentState.NOMINAL
                if snap.health.get("gyro") and snap.health.get("accel")
                else ComponentState.DEGRADED
            )
        mode = _MODE_MAP.get(snap.flight_mode, FlightMode.UNKNOWN)
        states["flight_control.core"] = (
            ComponentState.OPERATIONAL if mode is not FlightMode.UNKNOWN else ComponentState.UNKNOWN
        )
        states["power.battery"] = (
            ComponentState.DEGRADED if snap.battery_remaining < 0.2 else ComponentState.NOMINAL
        )
        for request in self._active.values():
            if request.subsystem in ("sensors.barometer",):
                states[request.subsystem] = (
                    ComponentState.UNAVAILABLE
                    if request.effect is Effect.UNAVAILABLE
                    else ComponentState.DEGRADED
                )
        return states

    async def health(self) -> HealthReport:
        return HealthReport(t=self._sim_time(), states=dict(self._states))

    async def snapshot(self) -> Snapshot:
        return Snapshot(
            t=self._sim_time(),
            states=dict(self._states),
            active_effects=tuple(self._active.values()),
            sample=None,
        )

    async def stop(self) -> None:
        self._stopped = True
        if self._link is not None and self._link.snapshot().connected:
            snap = self._link.snapshot()
            if snap.armed or snap.in_air:
                await self._link.land()
                self._log.append("stop: land command issued")
            await self._link.disconnect()

    async def collect_artifacts(self) -> list[ArtifactBlob]:
        status = "\n".join(self._link.snapshot().status_texts) if self._link else ""
        return [
            ArtifactBlob(
                name="px4-adapter.log",
                content_type="text/plain",
                data=("\n".join(self._log) + "\n").encode("utf-8"),
                description="PX4 adapter log (connection, mission upload, injections)",
            ),
            ArtifactBlob(
                name="px4-statustext.log",
                content_type="text/plain",
                data=(status + "\n").encode("utf-8"),
                description="STATUSTEXT messages received from PX4",
            ),
        ]


def _param_seconds(value: object, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        from reslab_core.duration import parse_duration

        try:
            return parse_duration(value)
        except ValueError:
            return default
    return default


def heading_deg(yaw_rad: float) -> float:
    return math.degrees(yaw_rad) % 360.0

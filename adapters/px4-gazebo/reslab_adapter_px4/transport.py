"""MAVLink transport abstraction.

`PX4Link` is the narrow interface the adapter needs. `MavsdkLink` implements it with the
MAVSDK gRPC Python wrapper (`mavsdk-grpc`, imported lazily so that runners without
simulation support never load it). Tests use an in-memory fake.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
from dataclasses import dataclass, field
from typing import Any, Protocol

from reslab_adapter_px4.mapping import FailureType, FailureUnit

EARTH_RADIUS = 6371000.0


@dataclass
class VehicleSnapshot:
    """Latest values gathered from telemetry subscriptions."""

    connected: bool = False
    latitude: float | None = None
    longitude: float | None = None
    altitude_msl: float | None = None
    relative_altitude: float | None = None
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    vn: float = 0.0
    ve: float = 0.0
    vd: float = 0.0
    flight_mode: str = "UNKNOWN"
    armed: bool = False
    in_air: bool = False
    landed_state: str = "UNKNOWN"
    battery_voltage: float = 0.0
    battery_remaining: float = 1.0
    gps_fix: str = "NO_GPS"
    gps_satellites: int = 0
    health: dict[str, bool] = field(default_factory=dict)
    mission_current: int = 0
    mission_total: int = 0
    mission_finished: bool = False
    status_texts: list[str] = field(default_factory=list)
    home_latitude: float | None = None
    home_longitude: float | None = None
    home_altitude_msl: float | None = None


@dataclass(frozen=True)
class GeodeticWaypoint:
    latitude: float
    longitude: float
    relative_altitude: float
    speed: float


def enu_to_geodetic(
    x: float, y: float, home_latitude: float, home_longitude: float
) -> tuple[float, float]:
    latitude = home_latitude + math.degrees(y / EARTH_RADIUS)
    longitude = home_longitude + math.degrees(
        x / (EARTH_RADIUS * math.cos(math.radians(home_latitude)))
    )
    return latitude, longitude


def geodetic_to_enu(
    latitude: float, longitude: float, home_latitude: float, home_longitude: float
) -> tuple[float, float]:
    y = math.radians(latitude - home_latitude) * EARTH_RADIUS
    x = (
        math.radians(longitude - home_longitude)
        * EARTH_RADIUS
        * math.cos(math.radians(home_latitude))
    )
    return x, y


class PX4Link(Protocol):
    async def connect(self, timeout: float) -> None: ...

    async def disconnect(self) -> None: ...

    async def set_param_int(self, name: str, value: int) -> None: ...

    async def upload_mission(self, waypoints: list[GeodeticWaypoint], rtl: bool) -> None: ...

    async def arm_and_start_mission(self) -> None: ...

    async def inject_failure(
        self, unit: FailureUnit, failure_type: FailureType, instance: int = 0
    ) -> tuple[bool, str]: ...

    async def land(self) -> None: ...

    def snapshot(self) -> VehicleSnapshot: ...

    @property
    def version(self) -> str: ...


class MavsdkLink:
    """PX4Link implemented with MAVSDK-Python."""

    def __init__(self, address: str) -> None:
        self.address = address
        self._system: Any = None
        self._tasks: list[asyncio.Task[None]] = []
        self._snapshot = VehicleSnapshot()
        self._version = "mavsdk"

    @property
    def version(self) -> str:
        return self._version

    def snapshot(self) -> VehicleSnapshot:
        return self._snapshot

    async def connect(self, timeout: float) -> None:
        from mavsdk_grpc import System

        try:
            import importlib.metadata as metadata

            self._version = f"mavsdk-grpc {metadata.version('mavsdk-grpc')}"
        except Exception:
            self._version = "mavsdk-grpc"
        self._system = System()

        async def _connect_and_wait() -> None:
            # System.connect() starts mavsdk_server and waits for its gRPC endpoint; when
            # the simulator address cannot be resolved the server never comes up, so the
            # whole sequence is bounded by the timeout, not only the discovery wait.
            await self._system.connect(system_address=self.address)
            async for state in self._system.core.connection_state():
                if state.is_connected:
                    return

        try:
            await asyncio.wait_for(_connect_and_wait(), timeout=timeout)
        except BaseException:
            await self.disconnect()
            raise
        self._snapshot.connected = True
        self._tasks = [
            asyncio.create_task(self._track_position()),
            asyncio.create_task(self._track_attitude()),
            asyncio.create_task(self._track_velocity()),
            asyncio.create_task(self._track_mode()),
            asyncio.create_task(self._track_armed()),
            asyncio.create_task(self._track_in_air()),
            asyncio.create_task(self._track_landed()),
            asyncio.create_task(self._track_battery()),
            asyncio.create_task(self._track_gps()),
            asyncio.create_task(self._track_health()),
            asyncio.create_task(self._track_mission_progress()),
            asyncio.create_task(self._track_status_text()),
            asyncio.create_task(self._track_home()),
        ]

    async def disconnect(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks = []
        self._snapshot.connected = False
        server = getattr(self._system, "_mavsdk_server", None)
        if server is not None:
            with contextlib.suppress(Exception):
                server.kill()
        self._system = None

    async def set_param_int(self, name: str, value: int) -> None:
        await self._system.param.set_param_int(name, value)

    async def upload_mission(self, waypoints: list[GeodeticWaypoint], rtl: bool) -> None:
        from mavsdk_grpc.mission import MissionItem, MissionPlan

        items = [
            MissionItem(
                wp.latitude,
                wp.longitude,
                wp.relative_altitude,
                wp.speed,
                True,  # is_fly_through
                float("nan"),  # gimbal pitch
                float("nan"),  # gimbal yaw
                MissionItem.CameraAction.NONE,
                float("nan"),  # loiter time
                float("nan"),  # camera photo interval
                float("nan"),  # acceptance radius
                float("nan"),  # yaw
                float("nan"),  # camera photo distance
                MissionItem.VehicleAction.NONE,
            )
            for wp in waypoints
        ]
        await self._system.mission.set_return_to_launch_after_mission(rtl)
        await self._system.mission.upload_mission(MissionPlan(items))

    async def arm_and_start_mission(self) -> None:
        await self._system.action.arm()
        await self._system.mission.start_mission()

    async def inject_failure(
        self, unit: FailureUnit, failure_type: FailureType, instance: int = 0
    ) -> tuple[bool, str]:
        from mavsdk_grpc.failure import FailureError
        from mavsdk_grpc.failure import FailureType as MavsdkFailureType
        from mavsdk_grpc.failure import FailureUnit as MavsdkFailureUnit

        try:
            await self._system.failure.inject(
                getattr(MavsdkFailureUnit, unit.value),
                getattr(MavsdkFailureType, failure_type.value),
                instance,
            )
        except FailureError as exc:
            return False, f"PX4 rejected failure injection: {exc}"
        return True, f"MAV_CMD_INJECT_FAILURE {unit.value} {failure_type.value} instance {instance}"

    async def land(self) -> None:
        with contextlib.suppress(Exception):
            await self._system.action.land()

    # ------------------------------------------------------------------ trackers

    async def _track_position(self) -> None:
        async for p in self._system.telemetry.position():
            self._snapshot.latitude = p.latitude_deg
            self._snapshot.longitude = p.longitude_deg
            self._snapshot.altitude_msl = p.absolute_altitude_m
            self._snapshot.relative_altitude = p.relative_altitude_m

    async def _track_attitude(self) -> None:
        async for a in self._system.telemetry.attitude_euler():
            self._snapshot.roll = math.radians(a.roll_deg)
            self._snapshot.pitch = math.radians(a.pitch_deg)
            self._snapshot.yaw = math.radians(a.yaw_deg)

    async def _track_velocity(self) -> None:
        async for v in self._system.telemetry.velocity_ned():
            self._snapshot.vn = v.north_m_s
            self._snapshot.ve = v.east_m_s
            self._snapshot.vd = v.down_m_s

    async def _track_mode(self) -> None:
        async for mode in self._system.telemetry.flight_mode():
            self._snapshot.flight_mode = str(mode).split(".")[-1]

    async def _track_armed(self) -> None:
        async for armed in self._system.telemetry.armed():
            self._snapshot.armed = bool(armed)

    async def _track_in_air(self) -> None:
        async for in_air in self._system.telemetry.in_air():
            self._snapshot.in_air = bool(in_air)

    async def _track_landed(self) -> None:
        async for state in self._system.telemetry.landed_state():
            self._snapshot.landed_state = str(state).split(".")[-1]

    async def _track_battery(self) -> None:
        async for battery in self._system.telemetry.battery():
            self._snapshot.battery_voltage = battery.voltage_v
            self._snapshot.battery_remaining = battery.remaining_percent

    async def _track_gps(self) -> None:
        async for info in self._system.telemetry.gps_info():
            self._snapshot.gps_fix = str(info.fix_type).split(".")[-1]
            self._snapshot.gps_satellites = info.num_satellites

    async def _track_health(self) -> None:
        async for health in self._system.telemetry.health():
            self._snapshot.health = {
                "gyro": health.is_gyrometer_calibration_ok,
                "accel": health.is_accelerometer_calibration_ok,
                "mag": health.is_magnetometer_calibration_ok,
                "local_position": health.is_local_position_ok,
                "global_position": health.is_global_position_ok,
                "home_position": health.is_home_position_ok,
                "armable": health.is_armable,
            }

    async def _track_mission_progress(self) -> None:
        async for progress in self._system.mission.mission_progress():
            self._snapshot.mission_current = progress.current
            self._snapshot.mission_total = progress.total
            self._snapshot.mission_finished = (
                progress.total > 0 and progress.current >= progress.total
            )

    async def _track_status_text(self) -> None:
        async for text in self._system.telemetry.status_text():
            self._snapshot.status_texts.append(f"{text.type}: {text.text}")
            del self._snapshot.status_texts[:-200]

    async def _track_home(self) -> None:
        async for home in self._system.telemetry.home():
            self._snapshot.home_latitude = home.latitude_deg
            self._snapshot.home_longitude = home.longitude_deg
            self._snapshot.home_altitude_msl = home.absolute_altitude_m

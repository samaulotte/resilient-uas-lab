"""Normalized telemetry and event model.

These models are the lingua franca between adapters, the runner, the control plane,
the analysis engines and the user interface. They are intentionally independent from
any simulator or middleware message definition (no ROS message, no MAVLink frame).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from reslab_core.states import (
    ComponentState,
    EventKind,
    EventSource,
    FlightMode,
    MissionPhase,
    Severity,
)

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
Metadata = Annotated[dict[str, Any], Field(default_factory=dict)]


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Position(BaseModel):
    """Local position in an East-North-Up frame relative to the mission origin (metres)."""

    model_config = ConfigDict(frozen=True)

    x: float = Field(description="East (m)")
    y: float = Field(description="North (m)")
    z: float = Field(description="Up, altitude above origin (m)")


class GeoPosition(BaseModel):
    model_config = ConfigDict(frozen=True)

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude_msl: float = Field(description="Altitude above mean sea level (m)")


class Attitude(BaseModel):
    model_config = ConfigDict(frozen=True)

    roll: float = Field(description="Roll angle (rad)")
    pitch: float = Field(description="Pitch angle (rad)")
    yaw: float = Field(description="Yaw / heading angle (rad, 0 = north, clockwise positive)")


class Velocity(BaseModel):
    model_config = ConfigDict(frozen=True)

    vx: float = Field(description="East velocity (m/s)")
    vy: float = Field(description="North velocity (m/s)")
    vz: float = Field(description="Up velocity (m/s)")

    @property
    def ground_speed(self) -> float:
        return (self.vx**2 + self.vy**2) ** 0.5


class MissionStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    phase: MissionPhase
    progress: float = Field(ge=0.0, le=1.0, description="Mission completion ratio")
    waypoint_index: int = Field(ge=0, description="Index of the waypoint currently targeted")
    waypoints_total: int = Field(ge=0)
    distance_to_waypoint: float | None = Field(default=None, description="Metres")


class FlightStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: FlightMode
    armed: bool
    control_authority: bool = Field(
        description="True while the flight core has full control of the vehicle"
    )
    autonomy: str = Field(
        default="mission",
        description="Which entity is currently driving the vehicle: mission, local, failsafe",
    )


class NavigationStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str = Field(description="Position source: gnss, dead_reckoning, none")
    gnss_fix: bool
    position_error: float = Field(ge=0, description="Estimated horizontal position error (m)")
    satellites: int | None = None


class CommunicationsStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    c2_link: bool
    telemetry_link: bool
    latency_ms: float | None = None
    packet_loss: float | None = Field(default=None, ge=0, le=1)


class PowerStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    voltage: float
    remaining: float = Field(ge=0, le=1)
    current: float | None = None


class TelemetrySample(BaseModel):
    """One normalized telemetry sample at a simulation instant."""

    model_config = ConfigDict(frozen=True)

    t: float = Field(ge=0, description="Simulation time (s)")
    wall_time: datetime = Field(default_factory=utcnow)
    source: str = Field(description="Adapter that produced the sample (mock, px4-gazebo, replay)")
    position: Position
    geo: GeoPosition | None = None
    attitude: Attitude
    velocity: Velocity
    mission: MissionStatus
    flight: FlightStatus
    navigation: NavigationStatus
    communications: CommunicationsStatus
    power: PowerStatus
    health: dict[str, ComponentState] = Field(
        default_factory=dict, description="Component states keyed by subsystem id"
    )


class RunEvent(BaseModel):
    """A discrete, classified event that happened during a run."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    sequence: int = Field(ge=0, description="Monotonic sequence number within the run")
    simulation_time: float = Field(ge=0)
    wall_time: datetime = Field(default_factory=utcnow)
    source: EventSource
    kind: EventKind
    event_type: str = Field(max_length=64, description="Machine readable type, snake_case")
    severity: Severity = Severity.INFO
    subsystem: str | None = None
    state_before: ComponentState | None = None
    state_after: ComponentState | None = None
    message: str = Field(max_length=500)
    scenario_event_id: str | None = Field(
        default=None, description="Scenario event this run event originates from"
    )
    metadata: Metadata

    @property
    def is_scenario_driven(self) -> bool:
        return self.source is EventSource.SCENARIO or self.scenario_event_id is not None


class ComponentStateChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    subsystem: str
    state_before: ComponentState
    state_after: ComponentState
    reason: str = ""
    caused_by: str | None = Field(default=None, description="Scenario event id if known")


class PlannedPath(BaseModel):
    """Mission plan as known before the run: waypoints in the local ENU frame."""

    model_config = ConfigDict(frozen=True)

    origin: GeoPosition | None = None
    waypoints: list[Position]
    safe_zone: Position | None = Field(default=None, description="Return / safe landing point")
    safe_zone_radius: float = Field(default=15.0, gt=0)

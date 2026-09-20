"""Shared builders for core unit tests (importable from every test module)."""

from __future__ import annotations

from pathlib import Path

from reslab_core.states import ComponentState, EventKind, EventSource, FlightMode, MissionPhase
from reslab_core.telemetry import (
    Attitude,
    CommunicationsStatus,
    FlightStatus,
    MissionStatus,
    NavigationStatus,
    Position,
    PowerStatus,
    RunEvent,
    TelemetrySample,
    Velocity,
)
from reslab_core.topology import DEFAULT_TOPOLOGY

SCENARIOS_DIR = Path(__file__).resolve().parents[3] / "scenarios"
RUN_ID = "00000000-0000-4000-8000-000000000001"


def healthy_states() -> dict[str, ComponentState]:
    return {c.id: c.healthy_state for c in DEFAULT_TOPOLOGY.components}


def make_sample(
    t: float,
    *,
    health: dict[str, ComponentState] | None = None,
    mode: FlightMode = FlightMode.MISSION,
    phase: MissionPhase = MissionPhase.ENROUTE,
    progress: float = 0.5,
    control_authority: bool = True,
    x: float = 0.0,
) -> TelemetrySample:
    return TelemetrySample(
        t=t,
        source="test",
        position=Position(x=x, y=0.0, z=30.0),
        attitude=Attitude(roll=0.0, pitch=0.0, yaw=0.0),
        velocity=Velocity(vx=5.0, vy=0.0, vz=0.0),
        mission=MissionStatus(phase=phase, progress=progress, waypoint_index=1, waypoints_total=4),
        flight=FlightStatus(mode=mode, armed=True, control_authority=control_authority),
        navigation=NavigationStatus(source="gnss", gnss_fix=True, position_error=0.5),
        communications=CommunicationsStatus(c2_link=True, telemetry_link=True),
        power=PowerStatus(voltage=16.0, remaining=0.9),
        health=health or healthy_states(),
    )


def make_event(
    seq: int,
    t: float,
    kind: EventKind,
    *,
    subsystem: str | None = None,
    before: ComponentState | None = None,
    after: ComponentState | None = None,
    scenario_event_id: str | None = None,
    metadata: dict | None = None,
    event_type: str = "state_change",
    source: EventSource = EventSource.ADAPTER,
) -> RunEvent:
    return RunEvent(
        run_id=RUN_ID,
        sequence=seq,
        simulation_time=t,
        source=source,
        kind=kind,
        event_type=event_type,
        subsystem=subsystem,
        state_before=before,
        state_after=after,
        message=f"{kind.value} {subsystem or ''}",
        scenario_event_id=scenario_event_id,
        metadata=metadata or {},
    )

"""Default mission geometry for the mock adapter."""

from __future__ import annotations

from reslab_core.scenario.model import Mission
from reslab_core.telemetry import GeoPosition, PlannedPath, Position

# Matches the default PX4 SITL home so replayed and simulated runs share a frame.
DEFAULT_ORIGIN = GeoPosition(latitude=47.397742, longitude=8.545594, altitude_msl=488.0)


def default_waypoints(altitude: float) -> list[Position]:
    """A survey-like loop of about 560 m total length."""

    return [
        Position(x=0.0, y=0.0, z=altitude),
        Position(x=90.0, y=30.0, z=altitude),
        Position(x=150.0, y=110.0, z=altitude),
        Position(x=80.0, y=170.0, z=altitude + 10.0),
        Position(x=-30.0, y=130.0, z=altitude + 10.0),
        Position(x=-50.0, y=40.0, z=altitude),
        Position(x=0.0, y=0.0, z=altitude),
    ]


def planned_path_for(mission: Mission) -> PlannedPath:
    if mission.waypoints:
        waypoints = [Position(x=0.0, y=0.0, z=mission.altitude)]
        waypoints += [Position(x=w.x, y=w.y, z=w.z) for w in mission.waypoints]
        waypoints.append(Position(x=0.0, y=0.0, z=mission.altitude))
    elif mission.type == "hover":
        waypoints = [Position(x=0.0, y=0.0, z=mission.altitude)] * 2
    else:
        waypoints = default_waypoints(mission.altitude)
    return PlannedPath(
        origin=DEFAULT_ORIGIN,
        waypoints=waypoints,
        safe_zone=Position(x=0.0, y=0.0, z=0.0),
        safe_zone_radius=15.0,
    )

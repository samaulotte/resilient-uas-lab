"""Descriptive catalog of adapters known to the platform.

This is metadata only (shown in the UI and the `/api/v1/system` endpoint). Whether an
adapter is actually available is reported live by runner heartbeats.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class AdapterStatus(StrEnum):
    AVAILABLE = "available"
    EXPERIMENTAL = "experimental"
    PLANNED = "planned"


class AdapterDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    display_name: str
    kind: str
    status: AdapterStatus
    description: str
    data_origin: str
    requirements: str = ""


ADAPTER_CATALOG: tuple[AdapterDescriptor, ...] = (
    AdapterDescriptor(
        name="mock",
        display_name="Mock simulator",
        kind="simulation",
        status=AdapterStatus.AVAILABLE,
        description=(
            "Deterministic component-state simulation of a multirotor with a companion "
            "computer. Runs anywhere, no flight stack required."
        ),
        data_origin="mock simulation",
    ),
    AdapterDescriptor(
        name="px4-gazebo",
        display_name="PX4 SITL + Gazebo",
        kind="simulation",
        status=AdapterStatus.EXPERIMENTAL,
        description=(
            "PX4 software-in-the-loop with Gazebo (Harmonic) running headless in the "
            "simulation profile. Effects are realised with PX4 failure injection and "
            "companion-side mechanisms."
        ),
        data_origin="PX4 SITL simulation",
        requirements="docker compose --profile sim (Linux host recommended)",
    ),
    AdapterDescriptor(
        name="replay",
        display_name="Replay",
        kind="replay",
        status=AdapterStatus.AVAILABLE,
        description="Re-emits the normalized telemetry and events of a recorded run.",
        data_origin="recorded run",
    ),
    AdapterDescriptor(
        name="px4-hitl",
        display_name="PX4 hardware-in-the-loop",
        kind="hitl",
        status=AdapterStatus.PLANNED,
        description="PX4 flight controller hardware on a bench, simulator providing sensors.",
        data_origin="bench hardware",
    ),
    AdapterDescriptor(
        name="ardupilot",
        display_name="ArduPilot SITL",
        kind="simulation",
        status=AdapterStatus.PLANNED,
        description="ArduPilot software-in-the-loop.",
        data_origin="ArduPilot SITL simulation",
    ),
    AdapterDescriptor(
        name="ros2",
        display_name="Generic ROS 2",
        kind="simulation",
        status=AdapterStatus.PLANNED,
        description="Generic ROS 2 robot adapter using lifecycle nodes and SROS2 enclaves.",
        data_origin="ROS 2 system",
    ),
)

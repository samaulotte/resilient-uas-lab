"""Runner protocol: messages exchanged between the control plane and runners.

Transport is an event bus (NATS JetStream in the reference deployment). Every message
carries `protocol_version` so that runners and control plane can be upgraded
independently.

Subjects (see `reslab_platform.bus.subjects` for the concrete strings):

- jobs: control plane -> runner pool (work queue)
- runs.<run_id>.lifecycle | events | telemetry | artifacts: runner -> control plane
- control.<run_id>: control plane -> runner (cancel)
- runners.heartbeat: runner -> control plane
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from reslab_core.states import RunState
from reslab_core.telemetry import PlannedPath, RunEvent, TelemetrySample, utcnow
from reslab_core.versions import PROTOCOL_VERSION

MAX_ARTIFACT_MESSAGE_BYTES = 4 * 1024 * 1024


class ProtocolMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    protocol_version: str = PROTOCOL_VERSION
    sent_at: datetime = Field(default_factory=utcnow)


class RunJob(ProtocolMessage):
    """Request to execute a validated scenario."""

    type: Literal["run_job"] = "run_job"
    run_id: str
    scenario_yaml: str = Field(description="Validated scenario document (canonical YAML)")
    scenario_hash: str
    adapter: str
    seed: int
    speed: float
    replay_source_run_id: str | None = Field(
        default=None, description="For the replay adapter: run whose telemetry is replayed"
    )


class LifecycleMessage(ProtocolMessage):
    type: Literal["lifecycle"] = "lifecycle"
    run_id: str
    state: RunState
    previous_state: RunState | None = None
    reason: str = ""
    runner_id: str
    simulation_time: float = 0.0
    planned_path: PlannedPath | None = None
    adapter_version: str | None = None
    data_origin: str | None = None


class EventMessage(ProtocolMessage):
    type: Literal["event"] = "event"
    run_id: str
    event: RunEvent


class TelemetryMessage(ProtocolMessage):
    """A batch of telemetry samples, ordered by simulation time."""

    type: Literal["telemetry"] = "telemetry"
    run_id: str
    sequence: int = Field(ge=0, description="Batch sequence number")
    samples: list[TelemetrySample] = Field(min_length=1, max_length=500)


class RunFinishedMessage(ProtocolMessage):
    """Final word of the runner: the run is over and no more messages will follow."""

    type: Literal["run_finished"] = "run_finished"
    run_id: str
    outcome: Literal["completed", "failed", "cancelled"]
    reason: str = ""
    runner_id: str
    simulation_time: float = 0.0
    event_count: int = 0
    sample_count: int = 0
    mission_complete: bool = False
    final_component_states: dict[str, str] = Field(default_factory=dict)


class ArtifactMessage(ProtocolMessage):
    """Small artifact produced by the runner, carried inline (base64)."""

    type: Literal["artifact"] = "artifact"
    run_id: str
    name: str
    content_type: str
    description: str = ""
    data_base64: str = Field(max_length=int(MAX_ARTIFACT_MESSAGE_BYTES * 4 / 3) + 4)


class RunnerHeartbeat(ProtocolMessage):
    type: Literal["heartbeat"] = "heartbeat"
    runner_id: str
    adapters: list[str]
    active_run_id: str | None = None
    version: str


class CancelRequest(ProtocolMessage):
    type: Literal["cancel"] = "cancel"
    run_id: str
    reason: str = "cancelled by user"

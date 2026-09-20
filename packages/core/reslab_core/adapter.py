"""Generic autonomous-system adapter contract.

The control plane never understands PX4, ArduPilot or ROS 2 internals. It speaks to a
target exclusively through this interface. An adapter translates generic scenario
effects into whatever mechanism the target supports and reports back normalized
telemetry, component states and events.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from reslab_core.scenario.catalog import Effect
from reslab_core.scenario.model import Mission, RecoveryPolicy, SimulationConfig, Target
from reslab_core.states import ComponentState
from reslab_core.telemetry import ComponentStateChange, PlannedPath, TelemetrySample
from reslab_core.topology import SystemTopology


class AdapterKind(StrEnum):
    SIMULATION = "simulation"
    HARDWARE_IN_THE_LOOP = "hitl"
    REPLAY = "replay"


class AdapterCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    kind: AdapterKind
    description: str
    vehicles: tuple[str, ...]
    supported_effects: dict[str, tuple[Effect, ...]] = Field(
        description="Effects the adapter can realise, keyed by subsystem id"
    )
    deterministic: bool = Field(description="Same seed and scenario reproduce the same run")
    real_time_capable: bool = True
    data_origin: str = Field(
        description="Human readable origin of telemetry, shown in the UI (never hardware here)"
    )

    def supports(self, subsystem: str, effect: Effect) -> bool:
        return effect in self.supported_effects.get(subsystem, ())


class AdapterConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    target: Target
    mission: Mission
    recovery: RecoveryPolicy
    simulation: SimulationConfig
    topology: SystemTopology


class InjectionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_event_id: str
    subsystem: str
    effect: Effect
    duration: float | None = Field(default=None, description="Seconds, None = until cleared")
    parameters: dict[str, float | int | str] = Field(default_factory=dict)


class InjectionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    applied: bool
    mechanism: str = Field(description="How the adapter realised the effect (for traceability)")
    detail: str = ""


class ClearRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_event_id: str
    subsystem: str
    effect: Effect


class HealthReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    t: float
    states: dict[str, ComponentState]


class Observation(BaseModel):
    """What the adapter observed since the last call: telemetry plus discrete changes."""

    model_config = ConfigDict(frozen=True)

    sample: TelemetrySample
    state_changes: tuple[ComponentStateChange, ...] = ()
    responses: tuple[SystemResponse, ...] = ()
    mission_events: tuple[MissionEvent, ...] = ()
    finished: bool = Field(default=False, description="Mission finished (complete or aborted)")


class SystemResponse(BaseModel):
    """An autonomous reaction of the target (failsafe, mode change, autonomy hand-over)."""

    model_config = ConfigDict(frozen=True)

    response_type: str
    message: str
    subsystem: str | None = None
    safe_state: bool = False


class MissionEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: str
    message: str
    progress: float = Field(ge=0, le=1)


class Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    t: float
    states: dict[str, ComponentState]
    active_effects: tuple[InjectionRequest, ...]
    sample: TelemetrySample | None


class ArtifactBlob(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    content_type: str
    data: bytes
    description: str = ""


SystemResponse.model_rebuild()
Observation.model_rebuild()


class AdapterError(Exception):
    """Raised by adapters for unrecoverable target failures."""


class AutonomousSystemAdapter(ABC):
    """Contract every target adapter implements.

    Lifecycle: `prepare` -> `start` -> (`observe`/`inject`/`clear`/`health`)* -> `stop`
    -> `collect_artifacts`.
    """

    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities: ...

    @abstractmethod
    async def prepare(self, configuration: AdapterConfiguration) -> PlannedPath:
        """Load the mission into the target and return the planned path."""

    @abstractmethod
    async def start(self) -> None:
        """Arm and start the mission. Simulation time starts at zero."""

    @abstractmethod
    async def inject(self, request: InjectionRequest) -> InjectionResult:
        """Apply an effect. Must never raise for unsupported effects; return applied=False."""

    @abstractmethod
    async def clear(self, request: ClearRequest) -> InjectionResult:
        """Remove a previously applied persistent effect."""

    @abstractmethod
    def observe(self) -> AsyncIterator[Observation]:
        """Stream observations at the configured telemetry rate until the mission ends."""

    @abstractmethod
    async def health(self) -> HealthReport:
        """Current component states."""

    @abstractmethod
    async def snapshot(self) -> Snapshot:
        """Full state for diagnostics and replay checkpoints."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the target and release resources. Idempotent."""

    @abstractmethod
    async def collect_artifacts(self) -> list[ArtifactBlob]:
        """Return logs and other artifacts produced by the target."""

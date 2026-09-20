"""Versioned report schema (`schema_version` 1.0).

`report.json` is the machine readable canonical output of a run. `report.html` is a
rendering of the same data. Everything an engineer needs to distinguish requested,
injected, observed and inferred information is present.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from reslab_core.analysis.assertions import AssertionResult
from reslab_core.analysis.metrics import MetricsResult
from reslab_core.analysis.scoring import ScoreResult
from reslab_core.provenance import Provenance
from reslab_core.states import BenchmarkResult, ComponentState, RunState
from reslab_core.telemetry import PlannedPath, Position, RunEvent
from reslab_core.topology import SystemTopology
from reslab_core.versions import REPORT_SCHEMA_VERSION


class ReportScenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    version: str
    api_version: str
    content_hash: str
    document: str = Field(description="Canonical YAML of the executed scenario")
    event_count: int
    assertion_count: int
    mission_timeout: str


class ReportTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    adapter: str
    adapter_version: str | None
    vehicle: str
    configuration: dict[str, str | int | float | bool]
    data_origin: str
    topology_id: str


class ReportRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: RunState
    started_at: datetime | None
    ended_at: datetime | None
    simulation_duration: float
    seed: int
    speed: float
    reason: str = ""


class ReportArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    content_type: str
    size_bytes: int
    storage_key: str
    description: str = ""
    sha256: str | None = None


class ComponentStateInterval(BaseModel):
    model_config = ConfigDict(frozen=True)

    subsystem: str
    state: ComponentState
    start: float
    end: float


class ReportSummary(BaseModel):
    """Headline figures generated from observed events (never hard-coded)."""

    model_config = ConfigDict(frozen=True)

    mission_complete: bool
    faults_injected: int
    faults_applied: int
    critical_failures: int
    recovered_subsystems: int
    degraded_transitions: int
    loss_of_control: bool
    safety_preservation: str = Field(pattern="^(PASS|FAIL)$")
    fault_containment: str = Field(pattern="^(PASS|FAIL)$")
    mean_time_to_recovery: float | None
    affected_domains: int


class PathPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    t: float
    x: float
    y: float
    z: float


class ResilienceReport(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "title": "ResilienceReport",
            "$id": "https://resilient-uas.dev/schemas/report/v1.json",
        },
    )

    schema_version: str = REPORT_SCHEMA_VERSION
    run_id: str
    generated_at: datetime
    scenario: ReportScenario
    target: ReportTarget
    run: ReportRun
    result: BenchmarkResult
    resilience_score: float = Field(ge=0, le=100)
    hard_gate_result: BenchmarkResult
    summary: ReportSummary
    score: ScoreResult
    metrics: MetricsResult
    assertions: list[AssertionResult]
    events: list[RunEvent]
    subsystem_timeline: list[ComponentStateInterval]
    planned_path: PlannedPath | None
    actual_path: list[PathPoint] = Field(description="Downsampled trajectory")
    topology: SystemTopology
    artifacts: list[ReportArtifact]
    provenance: Provenance


def downsample_positions(points: list[PathPoint], limit: int = 600) -> list[PathPoint]:
    if len(points) <= limit:
        return points
    step = len(points) / limit
    sampled = [points[int(i * step)] for i in range(limit)]
    if sampled[-1] is not points[-1]:
        sampled.append(points[-1])
    return sampled


def position_point(t: float, position: Position) -> PathPoint:
    return PathPoint(t=t, x=position.x, y=position.y, z=position.z)

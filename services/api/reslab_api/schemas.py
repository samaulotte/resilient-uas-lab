"""Request and response models of the versioned API (v1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from reslab_core.adapters_catalog import AdapterDescriptor
from reslab_core.analysis.assertions import AssertionResult
from reslab_core.analysis.metrics import MetricsResult
from reslab_core.analysis.scoring import ScoreProfile, ScoreResult
from reslab_core.report.model import ReportSummary
from reslab_core.scenario.catalog import Effect
from reslab_core.scenario.errors import ValidationIssue
from reslab_core.states import BenchmarkResult, ComponentState, RunState
from reslab_core.telemetry import PlannedPath, RunEvent, TelemetrySample
from reslab_core.topology import SystemTopology


class ApiError(BaseModel):
    error: str
    detail: str = ""
    issues: list[ValidationIssue] = Field(default_factory=list)


# ------------------------------------------------------------------ system


class ParameterSpecOut(BaseModel):
    name: str
    type: str
    description: str
    minimum: float | None = None
    maximum: float | None = None


class CatalogEntryOut(BaseModel):
    subsystem: str
    name: str
    domain: str
    category: str
    trust_zone: str
    healthy_state: ComponentState
    critical: bool
    description: str
    effects: list[Effect]


class EffectDescriptor(BaseModel):
    effect: Effect
    transient: bool
    duration_required: bool
    parameters: list[ParameterSpecOut]
    description: str


class RunnerOut(BaseModel):
    runner_id: str
    adapters: list[str]
    version: str
    active_run_id: str | None
    last_heartbeat_at: datetime
    online: bool


class AdapterOut(AdapterDescriptor):
    online: bool
    runners: list[str]


class ComponentHealth(BaseModel):
    database: bool
    bus: bool
    artifact_store: bool


class SystemInfo(BaseModel):
    software_version: str
    scenario_api_version: str
    report_schema_version: str
    protocol_version: str
    git_commit: str | None
    environment: str
    health: ComponentHealth
    topology: SystemTopology
    catalog: list[CatalogEntryOut]
    effects: list[EffectDescriptor]
    adapters: list[AdapterOut]
    runners: list[RunnerOut]
    score_profiles: list[ScoreProfile]
    counts: dict[str, int]
    component_states: list[ComponentState]
    run_states: list[RunState]


# ------------------------------------------------------------------ scenarios


class ScenarioSummary(BaseModel):
    name: str
    description: str
    version: str
    adapter: str
    tags: list[str]
    content_hash: str
    event_count: int
    assertion_count: int
    source: str
    updated_at: datetime
    last_run: RunSummary | None = None


class ScenarioDetail(ScenarioSummary):
    document: str
    scenario: dict[str, Any] = Field(description="Parsed scenario (canonical JSON)")
    expanded_events: list[dict[str, Any]]
    warnings: list[ValidationIssue]


class ScenarioValidateRequest(BaseModel):
    document: str = Field(max_length=256 * 1024)


class ScenarioValidateResponse(BaseModel):
    valid: bool
    issues: list[ValidationIssue]
    warnings: list[ValidationIssue]
    scenario: dict[str, Any] | None = None
    canonical_yaml: str | None = None
    content_hash: str | None = None
    expanded_events: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioCreateRequest(BaseModel):
    document: str = Field(max_length=256 * 1024)
    overwrite: bool = False


# ------------------------------------------------------------------ runs


class RunCreateRequest(BaseModel):
    scenario_name: str | None = Field(default=None, max_length=64)
    document: str | None = Field(default=None, max_length=256 * 1024)
    adapter: Literal["mock", "px4-gazebo", "replay"] | None = None
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)
    speed: float | None = Field(default=None, ge=0.1, le=100.0)
    label: str = Field(default="", max_length=120)
    replay_source_run_id: str | None = None


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scenario_name: str
    scenario_version: str
    scenario_hash: str
    adapter: str
    vehicle: str
    label: str
    state: RunState
    reason: str
    seed: int
    speed: float
    runner_id: str | None
    result: BenchmarkResult | None
    hard_gate_result: BenchmarkResult | None
    resilience_score: float | None
    summary: ReportSummary | None
    event_count: int
    sample_count: int
    last_simulation_time: float
    mission_complete: bool
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    updated_at: datetime
    replay_source_run_id: str | None = None


class RunDetail(RunSummary):
    scenario_document: str
    planned_path: PlannedPath | None
    provenance: dict[str, Any]
    artifacts: list[ArtifactOut]
    report_available: bool


class RunListResponse(BaseModel):
    runs: list[RunSummary]
    total: int
    limit: int
    offset: int


class ArtifactOut(BaseModel):
    name: str
    content_type: str
    size_bytes: int
    storage_key: str
    sha256: str | None
    description: str
    url: str


class EventsResponse(BaseModel):
    run_id: str
    events: list[RunEvent]
    count: int
    next_after_sequence: int | None


class TelemetryResponse(BaseModel):
    run_id: str
    samples: list[TelemetrySample]
    count: int
    total: int
    stride: int
    complete: bool


class MetricsResponse(BaseModel):
    run_id: str
    metrics: MetricsResult
    context: dict[str, float | bool | int | None]
    score: ScoreResult
    assertions: list[AssertionResult]


class CancelResponse(BaseModel):
    run: RunSummary
    delivered: bool


# ------------------------------------------------------------------ compare


class MetricComparison(BaseModel):
    key: str
    label: str
    unit: Literal["percent", "seconds", "count", "score", "bool"]
    better: Literal["higher", "lower", "neutral"]
    baseline: float | bool | int | None
    candidate: float | bool | int | None
    delta: float | None
    verdict: Literal["improvement", "regression", "unchanged", "changed", "not_comparable"]


class AssertionComparison(BaseModel):
    expression: str
    severity: str
    baseline: str | None
    candidate: str | None
    verdict: Literal["improvement", "regression", "unchanged", "changed", "not_comparable"]


class DimensionComparison(BaseModel):
    dimension: str
    label: str
    weight: int
    baseline: float | None
    candidate: float | None
    delta: float | None
    verdict: Literal["improvement", "regression", "unchanged", "not_comparable"]


class CompareResponse(BaseModel):
    baseline: RunSummary
    candidate: RunSummary
    same_scenario: bool
    same_scenario_hash: bool
    metrics: list[MetricComparison]
    dimensions: list[DimensionComparison]
    assertions: list[AssertionComparison]
    baseline_events: list[RunEvent]
    candidate_events: list[RunEvent]
    regressions: int
    improvements: int
    verdict: Literal["regression", "improvement", "unchanged", "mixed", "not_comparable"]


# ------------------------------------------------------------------ websocket


class StreamSnapshot(BaseModel):
    type: Literal["snapshot"] = "snapshot"
    run: RunDetail
    events: list[RunEvent]
    telemetry: list[TelemetrySample]
    server_time: datetime


class StreamCompleted(BaseModel):
    type: Literal["completed"] = "completed"
    run: RunSummary
    report_available: bool


class StreamHeartbeat(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"
    server_time: datetime


ScenarioSummary.model_rebuild()
ScenarioDetail.model_rebuild()
RunDetail.model_rebuild()

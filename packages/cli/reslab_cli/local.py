"""In-process execution of a scenario with the mock adapter (no platform required).

Used by `reslab run --local`, by CI to produce a resilience report without the control
plane, and as a quick way to iterate on scenarios.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from reslab_adapter_mock import MockAdapter
from reslab_core.analysis.scoring import DEFAULT_SCORE_PROFILE, ScoreProfile
from reslab_core.engine import ScenarioEngine
from reslab_core.ids import new_run_id
from reslab_core.provenance import Provenance
from reslab_core.report import ReportArtifact, build_report, render_html_report
from reslab_core.report.model import ResilienceReport
from reslab_core.scenario import ResilienceScenario, scenario_content_hash
from reslab_core.states import RunState
from reslab_core.telemetry import PlannedPath, RunEvent, TelemetrySample
from reslab_core.versions import SOFTWARE_VERSION


@dataclass
class LocalRunResult:
    run_id: str
    report: ResilienceReport
    events: list[RunEvent]
    samples: list[TelemetrySample]
    planned_path: PlannedPath | None
    output_dir: Path | None = None
    written: list[Path] = field(default_factory=list)


class _CollectingSink:
    def __init__(self, on_event=None) -> None:
        self.events: list[RunEvent] = []
        self.samples: list[TelemetrySample] = []
        self.states: list[RunState] = []
        self._on_event = on_event

    async def on_lifecycle(self, state, *, reason="", simulation_time=0.0, planned_path=None):
        self.states.append(state)

    async def on_event(self, event: RunEvent) -> None:
        self.events.append(event)
        if self._on_event is not None:
            self._on_event(event)

    async def on_telemetry(self, samples: list[TelemetrySample]) -> None:
        self.samples.extend(samples)


async def run_locally(
    scenario: ResilienceScenario,
    document: str,
    *,
    seed: int | None = None,
    speed: float = 50.0,
    output_dir: Path | None = None,
    score_profile: ScoreProfile = DEFAULT_SCORE_PROFILE,
    on_event=None,
) -> LocalRunResult:
    if scenario.target.adapter != "mock":
        raise ValueError(
            f"local execution supports the mock adapter only (scenario targets "
            f"'{scenario.target.adapter}'); use the platform for other adapters"
        )
    run_id = new_run_id()
    sink = _CollectingSink(on_event)
    started_at = datetime.now(tz=UTC)
    engine = ScenarioEngine(
        run_id=run_id, scenario=scenario, adapter=MockAdapter(), sink=sink, seed=seed, speed=speed
    )
    result = await engine.run()
    ended_at = datetime.now(tz=UTC)
    content_hash = scenario_content_hash(document)
    provenance = Provenance(
        scenario_hash=content_hash,
        scenario_version=scenario.metadata.version,
        adapter="mock",
        adapter_version="0.1.0",
        seed=engine.seed,
        speed=engine.speed,
        started_at=started_at,
        ended_at=ended_at,
        runner_id="local-cli",
        environment={"software_version": SOFTWARE_VERSION, "execution": "reslab run --local"},
        data_origin="mock simulation",
    )
    final_state = (
        RunState.COMPLETED
        if result.final_state is RunState.COLLECTING
        else (RunState.CANCELLED if result.final_state is RunState.CANCELLED else RunState.FAILED)
    )
    artifacts: list[ReportArtifact] = []
    report = build_report(
        run_id=run_id,
        scenario=scenario,
        scenario_hash=content_hash,
        events=sink.events,
        samples=sink.samples,
        provenance=provenance,
        run_state=final_state,
        started_at=started_at,
        ended_at=ended_at,
        reason=result.reason,
        planned_path=result.planned_path,
        artifacts=artifacts,
        score_profile=score_profile,
    )
    local = LocalRunResult(
        run_id=run_id,
        report=report,
        events=sink.events,
        samples=sink.samples,
        planned_path=result.planned_path,
    )
    if output_dir is not None:
        target = output_dir / run_id if output_dir.name != run_id else output_dir
        target.mkdir(parents=True, exist_ok=True)
        json_path = target / "report.json"
        json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        html_path = target / "report.html"
        html_path.write_text(render_html_report(report), encoding="utf-8")
        events_path = target / "events.json"
        events_path.write_text(
            json.dumps([e.model_dump(mode="json") for e in sink.events], indent=1), encoding="utf-8"
        )
        scenario_path = target / "scenario.yaml"
        scenario_path.write_text(document, encoding="utf-8")
        for blob in result.artifacts:
            blob_path = target / blob.name
            blob_path.write_bytes(blob.data)
            local.written.append(blob_path)
        local.output_dir = target
        local.written = [json_path, html_path, events_path, scenario_path, *local.written]
    return local

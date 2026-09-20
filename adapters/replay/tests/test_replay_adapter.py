from __future__ import annotations

from pathlib import Path

from reslab_adapter_mock import MockAdapter
from reslab_adapter_replay import FileReplaySource, ReplayAdapter, ReplayRecording
from reslab_core.analysis.metrics import compute_metrics
from reslab_core.engine import ScenarioEngine
from reslab_core.scenario import load_scenario_file
from reslab_core.states import RunState

SCENARIOS = Path(__file__).resolve().parents[3] / "scenarios"
RUN_ID = "00000000-0000-4000-8000-00000000000a"


class Sink:
    def __init__(self) -> None:
        self.events = []
        self.samples = []

    async def on_lifecycle(self, state, *, reason="", simulation_time=0.0, planned_path=None):
        pass

    async def on_event(self, event):
        self.events.append(event)

    async def on_telemetry(self, samples):
        self.samples.extend(samples)


async def test_replay_reproduces_recorded_run(tmp_path: Path) -> None:
    scenario = load_scenario_file(SCENARIOS / "mission-compute-restart.yaml")
    original = Sink()
    result = await ScenarioEngine(
        run_id=RUN_ID, scenario=scenario, adapter=MockAdapter(), sink=original, speed=100.0
    ).run()
    assert result.final_state is RunState.COLLECTING
    recording = ReplayRecording(
        source_run_id=RUN_ID,
        source_adapter="mock",
        scenario_name=scenario.metadata.name,
        planned_path=result.planned_path,
        samples=original.samples,
        events=original.events,
    )
    path = tmp_path / "recording.json"
    path.write_text(recording.model_dump_json())

    replayed = Sink()
    adapter = ReplayAdapter(FileReplaySource(path))
    result2 = await ScenarioEngine(
        run_id=RUN_ID, scenario=scenario, adapter=adapter, sink=replayed, speed=100.0
    ).run()
    assert result2.final_state is RunState.COLLECTING
    assert len(replayed.samples) == len(original.samples)
    assert all(s.source == "replay:mock" for s in replayed.samples)

    m1 = compute_metrics(events=original.events, samples=original.samples)
    m2 = compute_metrics(events=replayed.events, samples=replayed.samples)
    assert m1.recovery.mean_time_to_recovery == m2.recovery.mean_time_to_recovery
    assert m1.mission.completion == m2.mission.completion
    assert m1.propagation.affected_components == m2.propagation.affected_components
    assert m1.availability == m2.availability
    artifacts = await adapter.collect_artifacts()
    assert artifacts[0].name == "replay-source.txt"

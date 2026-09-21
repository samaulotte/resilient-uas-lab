from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from reslab_adapter_replay.sources import ReplayRecording, ReplaySource
from reslab_core.adapter import (
    AdapterCapabilities,
    AdapterConfiguration,
    AdapterKind,
    ArtifactBlob,
    AutonomousSystemAdapter,
    ClearRequest,
    HealthReport,
    InjectionRequest,
    InjectionResult,
    MissionEvent,
    Observation,
    Snapshot,
    SystemResponse,
)
from reslab_core.scenario.catalog import DEFAULT_CATALOG
from reslab_core.states import ComponentState, EventKind, MissionPhase
from reslab_core.telemetry import ComponentStateChange, PlannedPath, TelemetrySample

REPLAY_ADAPTER_VERSION = "0.2.0"

REPLAY_CAPABILITIES = AdapterCapabilities(
    name="replay",
    kind=AdapterKind.REPLAY,
    description=(
        "Re-emits the normalized telemetry and events of a recorded run. Injections are "
        "accepted as 'recorded': the replay never alters the recording."
    ),
    vehicles=("x500", "generic-multirotor"),
    supported_effects={entry.component.id: entry.effects for entry in DEFAULT_CATALOG.entries},
    deterministic=True,
    real_time_capable=True,
    data_origin="replay of a recorded run (no live target)",
)


class ReplayAdapter(AutonomousSystemAdapter):
    def __init__(self, source: ReplaySource) -> None:
        self.source = source
        self._recording: ReplayRecording | None = None
        self._speed = 1.0
        self._stopped = False
        self._states: dict[str, ComponentState] = {}
        self._t = 0.0

    @property
    def capabilities(self) -> AdapterCapabilities:
        return REPLAY_CAPABILITIES.model_copy(
            update={"data_origin": f"replay of recording {self.source.describe()}"}
        )

    @property
    def recording(self) -> ReplayRecording:
        if self._recording is None:
            raise RuntimeError("adapter not prepared")
        return self._recording

    async def prepare(self, configuration: AdapterConfiguration) -> PlannedPath:
        self._recording = await self.source.load()
        self._speed = configuration.simulation.speed
        first = self.recording.samples[0]
        self._states = {c.id: c.healthy_state for c in configuration.topology.components}
        self._states.update(first.health)
        self._stopped = False
        planned = self.recording.planned_path
        if planned is None:
            step = max(1, len(self.recording.samples) // 12)
            planned = PlannedPath(
                waypoints=[s.position for s in self.recording.samples[::step]],
            )
        return planned

    async def start(self) -> None:
        return None

    async def inject(self, request: InjectionRequest) -> InjectionResult:
        return InjectionResult(
            applied=True,
            mechanism="replay:recorded",
            detail="effect is part of the recording; states come from recorded telemetry",
        )

    async def clear(self, request: ClearRequest) -> InjectionResult:
        return InjectionResult(applied=True, mechanism="replay:recorded")

    async def observe(self) -> AsyncIterator[Observation]:
        recording = self.recording
        responses_by_t: dict[float, list[SystemResponse]] = {}
        mission_by_t: dict[float, list[MissionEvent]] = {}
        for event in recording.events:
            if event.kind is EventKind.SYSTEM_RESPONSE:
                responses_by_t.setdefault(event.simulation_time, []).append(
                    SystemResponse(
                        response_type=event.event_type,
                        message=event.message,
                        subsystem=event.subsystem,
                        safe_state=bool(event.metadata.get("safe_state", False)),
                    )
                )
            elif event.kind is EventKind.MISSION and event.event_type in (
                "waypoint_reached",
                "takeoff_complete",
                "landed",
            ):
                mission_by_t.setdefault(event.simulation_time, []).append(
                    MissionEvent(
                        event_type=event.event_type,
                        message=event.message,
                        progress=float(event.metadata.get("progress", 0.0) or 0.0),
                    )
                )
        wall_start = time.monotonic()
        t0 = recording.samples[0].t
        last_index = len(recording.samples) - 1
        pending_t: list[float] = sorted(set(responses_by_t) | set(mission_by_t))
        for index, sample in enumerate(recording.samples):
            if self._stopped:
                return
            previous_t = self._t
            self._t = sample.t
            changes: list[ComponentStateChange] = []
            for subsystem, state in sample.health.items():
                before = self._states.get(subsystem, ComponentState.UNKNOWN)
                if before != state:
                    changes.append(
                        ComponentStateChange(
                            subsystem=subsystem,
                            state_before=before,
                            state_after=state,
                            reason="recorded",
                        )
                    )
                    self._states[subsystem] = state
            responses: list[SystemResponse] = []
            mission_events: list[MissionEvent] = []
            while (
                pending_t and pending_t[0] <= sample.t and (pending_t[0] > previous_t or index == 0)
            ):
                t_event = pending_t.pop(0)
                responses.extend(responses_by_t.get(t_event, []))
                mission_events.extend(mission_by_t.get(t_event, []))
            finished = index == last_index or sample.mission.phase in (
                MissionPhase.COMPLETE,
                MissionPhase.ABORTED,
            )
            replayed = sample.model_copy(update={"source": f"replay:{sample.source}"})
            yield Observation(
                sample=replayed,
                state_changes=tuple(changes),
                responses=tuple(responses),
                mission_events=tuple(mission_events),
                finished=finished,
            )
            if finished:
                return
            if self._speed > 0:
                due = wall_start + (sample.t - t0) / self._speed
                delay = due - time.monotonic()
                if delay > 0.0005:
                    await asyncio.sleep(min(delay, 0.5))
                else:
                    await asyncio.sleep(0)

    async def health(self) -> HealthReport:
        return HealthReport(t=self._t, states=dict(self._states))

    async def snapshot(self) -> Snapshot:
        return Snapshot(t=self._t, states=dict(self._states), active_effects=(), sample=None)

    async def stop(self) -> None:
        self._stopped = True

    async def collect_artifacts(self) -> list[ArtifactBlob]:
        if self._recording is None:
            return []
        info = (
            f"source={self.source.describe()}\nsource_run_id={self._recording.source_run_id}\n"
            f"source_adapter={self._recording.source_adapter}\nsamples={len(self._recording.samples)}\n"
        )
        return [
            ArtifactBlob(
                name="replay-source.txt",
                content_type="text/plain",
                data=info.encode("utf-8"),
                description="Provenance of the replayed recording",
            )
        ]


def recording_from_samples(
    samples: list[TelemetrySample], events: list | None = None, **kwargs: object
) -> ReplayRecording:
    return ReplayRecording(samples=samples, events=list(events or []), **kwargs)  # type: ignore[arg-type]

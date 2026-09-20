"""Engine sink that publishes run progress to the event bus."""

from __future__ import annotations

from reslab_core.protocol import EventMessage, LifecycleMessage, TelemetryMessage
from reslab_core.states import RunState
from reslab_core.telemetry import PlannedPath, RunEvent, TelemetrySample
from reslab_platform.bus import Bus, Subjects


class BusSink:
    def __init__(
        self,
        bus: Bus,
        *,
        run_id: str,
        runner_id: str,
        adapter_version: str | None,
        data_origin: str | None,
    ) -> None:
        self.bus = bus
        self.run_id = run_id
        self.runner_id = runner_id
        self.adapter_version = adapter_version
        self.data_origin = data_origin
        self._telemetry_sequence = 0
        self._previous: RunState | None = None
        self.event_count = 0
        self.sample_count = 0

    async def on_lifecycle(
        self,
        state: RunState,
        *,
        reason: str = "",
        simulation_time: float = 0.0,
        planned_path: PlannedPath | None = None,
    ) -> None:
        message = LifecycleMessage(
            run_id=self.run_id,
            state=state,
            previous_state=self._previous,
            reason=reason,
            runner_id=self.runner_id,
            simulation_time=simulation_time,
            planned_path=planned_path,
            adapter_version=self.adapter_version,
            data_origin=self.data_origin,
        )
        self._previous = state
        await self.bus.publish_js(Subjects.run_lifecycle(self.run_id), message)

    async def on_event(self, event: RunEvent) -> None:
        self.event_count += 1
        await self.bus.publish_js(
            Subjects.run_events(self.run_id), EventMessage(run_id=self.run_id, event=event)
        )

    async def on_telemetry(self, samples: list[TelemetrySample]) -> None:
        if not samples:
            return
        self.sample_count += len(samples)
        message = TelemetryMessage(
            run_id=self.run_id, sequence=self._telemetry_sequence, samples=samples
        )
        self._telemetry_sequence += 1
        await self.bus.publish_js(Subjects.run_telemetry(self.run_id), message)

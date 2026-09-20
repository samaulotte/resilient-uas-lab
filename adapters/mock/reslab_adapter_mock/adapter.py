"""`MockAdapter`: the adapter contract implemented over `MockSimulation`."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from reslab_adapter_mock.mission import planned_path_for
from reslab_adapter_mock.simulation import MockSimulation
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
    Observation,
    Snapshot,
)
from reslab_core.scenario.catalog import DEFAULT_CATALOG
from reslab_core.telemetry import PlannedPath

MOCK_ADAPTER_VERSION = "0.1.0"

MOCK_CAPABILITIES = AdapterCapabilities(
    name="mock",
    kind=AdapterKind.SIMULATION,
    description=(
        "Deterministic component-state simulator of a multirotor with a companion "
        "computer. No physics engine, no flight stack: every effect in the fault "
        "catalog is realised by the mock's documented behavioural model."
    ),
    vehicles=("x500", "generic-multirotor"),
    supported_effects={entry.component.id: entry.effects for entry in DEFAULT_CATALOG.entries},
    deterministic=True,
    real_time_capable=True,
    data_origin="mock simulation (no flight stack, no hardware)",
)


class MockAdapter(AutonomousSystemAdapter):
    def __init__(self, *, max_sleep: float = 0.5) -> None:
        self._sim: MockSimulation | None = None
        self._speed = 1.0
        self._planned: PlannedPath | None = None
        self._stopped = False
        self._max_sleep = max_sleep
        self._injections: list[dict[str, object]] = []

    @property
    def capabilities(self) -> AdapterCapabilities:
        return MOCK_CAPABILITIES

    @property
    def simulation(self) -> MockSimulation:
        if self._sim is None:
            raise RuntimeError("adapter not prepared")
        return self._sim

    async def prepare(self, configuration: AdapterConfiguration) -> PlannedPath:
        self._planned = planned_path_for(configuration.mission)
        self._speed = configuration.simulation.speed
        self._sim = MockSimulation(
            seed=configuration.simulation.seed,
            mission=configuration.mission,
            recovery=configuration.recovery,
            planned_path=self._planned,
            rate_hz=configuration.simulation.telemetry_rate_hz,
            topology=configuration.topology,
        )
        self._stopped = False
        return self._planned

    async def start(self) -> None:
        self.simulation.start()

    async def inject(self, request: InjectionRequest) -> InjectionResult:
        result = self.simulation.inject(request)
        self._injections.append(
            {
                "t": self.simulation.t,
                "event": request.scenario_event_id,
                "subsystem": request.subsystem,
                "effect": request.effect.value,
                "applied": result.applied,
            }
        )
        return result

    async def clear(self, request: ClearRequest) -> InjectionResult:
        return self.simulation.clear(request)

    async def observe(self) -> AsyncIterator[Observation]:
        sim = self.simulation
        wall_start = time.monotonic()
        sim_start = sim.t
        while not self._stopped:
            observation = sim.step()
            yield observation
            if observation.finished:
                return
            # Pace against wall time so speed factors stay accurate over long runs.
            if self._speed > 0:
                due = wall_start + (sim.t - sim_start) / self._speed
                delay = due - time.monotonic()
                if delay > 0.0005:
                    await asyncio.sleep(min(delay, self._max_sleep))
                else:
                    await asyncio.sleep(0)

    async def health(self) -> HealthReport:
        sim = self.simulation
        return HealthReport(t=sim.t, states=sim.health())

    async def snapshot(self) -> Snapshot:
        sim = self.simulation
        active = tuple(
            InjectionRequest(
                scenario_event_id=e.event_id,
                subsystem=e.subsystem,
                effect=e.effect,
                duration=e.duration,
                parameters=e.parameters,
            )
            for e in sim.effects.values()
        )
        return Snapshot(t=sim.t, states=sim.health(), active_effects=active, sample=None)

    async def stop(self) -> None:
        self._stopped = True

    async def collect_artifacts(self) -> list[ArtifactBlob]:
        sim = self._sim
        if sim is None:
            return []
        log = "\n".join(sim.log) + "\n"
        return [
            ArtifactBlob(
                name="mock-adapter.log",
                content_type="text/plain",
                data=log.encode("utf-8"),
                description="Mock adapter internal log (injections, mode changes)",
            ),
            ArtifactBlob(
                name="mock-injections.json",
                content_type="application/json",
                data=json.dumps(self._injections, indent=2).encode("utf-8"),
                description="Injection requests as seen by the mock adapter",
            ),
        ]

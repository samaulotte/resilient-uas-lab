"""Fault catalog: which effects may be injected into which subsystem.

Effects are abstract consequences. They never describe how a disturbance is produced,
only what the target system experiences. The catalog is the authoritative whitelist
used by scenario validation and exposed to the Scenario Studio.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from reslab_core.topology import DEFAULT_TOPOLOGY, Component, FaultCategory, SystemTopology


class Effect(StrEnum):
    UNAVAILABLE = "unavailable"
    INTERMITTENT = "intermittent"
    DEGRADED = "degraded"
    ERRONEOUS = "erroneous"
    STUCK = "stuck"
    RESTART = "restart"
    CRASH = "crash"
    LATENCY = "latency"
    PACKET_LOSS = "packet_loss"
    RESOURCE_PRESSURE = "resource_pressure"
    TEMPORARY_DISCONNECT = "temporary_disconnect"


# Effects that stay active until cleared (optionally bounded by `duration`).
PERSISTENT_EFFECTS: frozenset[Effect] = frozenset(
    {
        Effect.UNAVAILABLE,
        Effect.INTERMITTENT,
        Effect.DEGRADED,
        Effect.ERRONEOUS,
        Effect.STUCK,
        Effect.LATENCY,
        Effect.PACKET_LOSS,
        Effect.RESOURCE_PRESSURE,
        Effect.TEMPORARY_DISCONNECT,
    }
)

# Effects that trigger a self-terminating transient; the target recovers on its own.
TRANSIENT_EFFECTS: frozenset[Effect] = frozenset({Effect.RESTART, Effect.CRASH})

# Effects that require a bounded duration.
DURATION_REQUIRED_EFFECTS: frozenset[Effect] = frozenset({Effect.TEMPORARY_DISCONNECT})


class ParameterSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    type: str = Field(pattern="^(number|integer|duration|ratio)$")
    description: str
    minimum: float | None = None
    maximum: float | None = None


EFFECT_PARAMETERS: dict[Effect, tuple[ParameterSpec, ...]] = {
    Effect.INTERMITTENT: (
        ParameterSpec(
            name="period",
            type="duration",
            description="Cycle period of the intermittent behaviour",
        ),
        ParameterSpec(
            name="duty_cycle",
            type="ratio",
            description="Fraction of each period during which the function is available",
            minimum=0.0,
            maximum=1.0,
        ),
    ),
    Effect.LATENCY: (
        ParameterSpec(
            name="latency_ms",
            type="number",
            description="Added one-way latency in milliseconds",
            minimum=0,
            maximum=60000,
        ),
    ),
    Effect.PACKET_LOSS: (
        ParameterSpec(
            name="loss_ratio",
            type="ratio",
            description="Fraction of messages dropped",
            minimum=0.0,
            maximum=1.0,
        ),
    ),
    Effect.RESOURCE_PRESSURE: (
        ParameterSpec(
            name="load",
            type="ratio",
            description="Fraction of compute capacity consumed by the pressure",
            minimum=0.0,
            maximum=1.0,
        ),
    ),
    Effect.DEGRADED: (
        ParameterSpec(
            name="level",
            type="ratio",
            description="Remaining capability as a fraction of nominal",
            minimum=0.0,
            maximum=1.0,
        ),
    ),
    Effect.RESTART: (
        ParameterSpec(
            name="restart_time",
            type="duration",
            description="Adapter hint for the expected restart time",
        ),
    ),
    Effect.CRASH: (
        ParameterSpec(
            name="watchdog_time",
            type="duration",
            description="Adapter hint for the watchdog delay before restart",
        ),
    ),
}


class CatalogEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    component: Component
    effects: tuple[Effect, ...]
    flight_critical_warning: bool = Field(
        default=False,
        description="Injecting into this subsystem targets the flight-critical domain",
    )


class FaultCatalog(BaseModel):
    model_config = ConfigDict(frozen=True)

    topology: SystemTopology
    entries: tuple[CatalogEntry, ...]

    def entry(self, subsystem: str) -> CatalogEntry | None:
        for e in self.entries:
            if e.component.id == subsystem:
                return e
        return None

    def allows(self, subsystem: str, effect: Effect) -> bool:
        entry = self.entry(subsystem)
        return entry is not None and effect in entry.effects

    def by_category(self) -> dict[FaultCategory, list[CatalogEntry]]:
        grouped: dict[FaultCategory, list[CatalogEntry]] = {}
        for e in self.entries:
            grouped.setdefault(e.component.category, []).append(e)
        return grouped


_COMMS_EFFECTS = (
    Effect.UNAVAILABLE,
    Effect.INTERMITTENT,
    Effect.DEGRADED,
    Effect.LATENCY,
    Effect.PACKET_LOSS,
    Effect.TEMPORARY_DISCONNECT,
)
_SENSOR_EFFECTS = (
    Effect.UNAVAILABLE,
    Effect.INTERMITTENT,
    Effect.DEGRADED,
    Effect.ERRONEOUS,
    Effect.STUCK,
)
_COMPUTE_EFFECTS = (
    Effect.RESTART,
    Effect.CRASH,
    Effect.RESOURCE_PRESSURE,
    Effect.DEGRADED,
    Effect.UNAVAILABLE,
)
_PROCESS_EFFECTS = (Effect.RESTART, Effect.CRASH, Effect.STUCK, Effect.DEGRADED)
_SERVICE_EFFECTS = (Effect.UNAVAILABLE, Effect.DEGRADED, Effect.LATENCY, Effect.RESTART)
_NETWORK_EFFECTS = (
    Effect.LATENCY,
    Effect.PACKET_LOSS,
    Effect.TEMPORARY_DISCONNECT,
    Effect.UNAVAILABLE,
    Effect.DEGRADED,
)

_EFFECTS_BY_COMPONENT: dict[str, tuple[Effect, ...]] = {
    "external.gcs": (Effect.UNAVAILABLE, Effect.TEMPORARY_DISCONNECT, Effect.LATENCY),
    "communications.c2": _COMMS_EFFECTS,
    "communications.telemetry": (*_COMMS_EFFECTS, Effect.RESTART),
    "mission.compute": _COMPUTE_EFFECTS,
    "mission.planner": _PROCESS_EFFECTS,
    "mission.services": _SERVICE_EFFECTS,
    "network.companion_link": _NETWORK_EFFECTS,
    "security.gateway": (Effect.UNAVAILABLE, Effect.DEGRADED, Effect.RESTART, Effect.LATENCY),
    "navigation.gnss": _SENSOR_EFFECTS,
    "navigation.estimator": (Effect.DEGRADED, Effect.ERRONEOUS),
    "sensors.barometer": _SENSOR_EFFECTS,
    "sensors.magnetometer": _SENSOR_EFFECTS,
    "sensors.imu": (Effect.DEGRADED, Effect.ERRONEOUS, Effect.INTERMITTENT),
    "flight_control.core": (Effect.DEGRADED, Effect.RESTART, Effect.RESOURCE_PRESSURE),
    "actuation.motors": (Effect.DEGRADED, Effect.INTERMITTENT),
    "power.battery": (Effect.DEGRADED, Effect.ERRONEOUS, Effect.INTERMITTENT),
    "power.bus": (Effect.DEGRADED, Effect.INTERMITTENT),
}


def default_catalog(topology: SystemTopology = DEFAULT_TOPOLOGY) -> FaultCatalog:
    entries: list[CatalogEntry] = []
    for component in topology.components:
        effects = _EFFECTS_BY_COMPONENT.get(component.id, ())
        entries.append(
            CatalogEntry(
                component=component,
                effects=effects,
                flight_critical_warning=component.critical,
            )
        )
    return FaultCatalog(topology=topology, entries=tuple(entries))


DEFAULT_CATALOG = default_catalog()

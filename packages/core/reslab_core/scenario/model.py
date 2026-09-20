"""Versioned scenario schema (`resilient-uas.dev/v1alpha1`, kind `ResilienceScenario`).

The YAML document is the authoritative, portable representation of a resilience test.
The schema is deliberately declarative: it names subsystems, effects, times and
expectations. It cannot express commands, code or file paths.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from reslab_core.analysis.expressions import ExpressionError, parse_expression
from reslab_core.duration import DurationError, parse_duration
from reslab_core.ids import EVENT_ID_RE, SLUG_RE, SUBSYSTEM_RE
from reslab_core.scenario.catalog import (
    DEFAULT_CATALOG,
    DURATION_REQUIRED_EFFECTS,
    EFFECT_PARAMETERS,
    TRANSIENT_EFFECTS,
    Effect,
)
from reslab_core.states import ComponentState, Severity
from reslab_core.versions import SCENARIO_KIND, SUPPORTED_SCENARIO_API_VERSIONS

DurationStr = Annotated[str, StringConstraints(min_length=2, max_length=32)]
Slug = Annotated[str, StringConstraints(pattern=SLUG_RE.pattern, max_length=64)]
SubsystemId = Annotated[str, StringConstraints(pattern=SUBSYSTEM_RE.pattern, max_length=65)]
EventId = Annotated[str, StringConstraints(pattern=EVENT_ID_RE.pattern, max_length=64)]
Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
ShortText = Annotated[str, StringConstraints(max_length=200)]
LongText = Annotated[str, StringConstraints(max_length=4000)]

ParameterValue = float | int
AdapterName = Literal["mock", "px4-gazebo", "replay"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


def _validate_duration_field(value: str, *, field: str) -> str:
    try:
        parse_duration(value)
    except DurationError as exc:
        raise ValueError(f"{field}: {exc}") from exc
    return value


class ScenarioMetadata(StrictModel):
    name: Slug = Field(description="Unique scenario name (kebab-case)")
    description: LongText = ""
    version: Annotated[str, StringConstraints(max_length=32)] = "1"
    labels: dict[Key, ShortText] = Field(default_factory=dict, max_length=16)
    tags: list[Slug] = Field(default_factory=list, max_length=16)


class Target(StrictModel):
    adapter: AdapterName = Field(description="Adapter used to execute the scenario")
    vehicle: Slug = Field(default="x500", description="Vehicle model identifier")
    configuration: dict[Key, ParameterValue | str | bool] = Field(
        default_factory=dict,
        max_length=32,
        description="Adapter-specific configuration (scalar values only)",
    )

    @field_validator("configuration")
    @classmethod
    def _bounded_strings(cls, value: dict[str, ParameterValue | str | bool]) -> dict:
        for key, item in value.items():
            if isinstance(item, str) and len(item) > 200:
                raise ValueError(f"configuration.{key}: string values are limited to 200 chars")
        return value


class Waypoint(StrictModel):
    x: float = Field(ge=-5000, le=5000, description="East offset from origin (m)")
    y: float = Field(ge=-5000, le=5000, description="North offset from origin (m)")
    z: float = Field(ge=1, le=500, description="Altitude above origin (m)")
    hold: DurationStr | None = Field(default=None, description="Hold time at the waypoint")

    @field_validator("hold")
    @classmethod
    def _hold_duration(cls, value: str | None) -> str | None:
        if value is not None:
            _validate_duration_field(value, field="hold")
        return value


class Mission(StrictModel):
    type: Literal["waypoint", "hover", "survey"] = "waypoint"
    timeout: DurationStr = Field(default="180s", description="Hard limit for the whole mission")
    cruise_speed: float = Field(default=6.0, gt=0, le=30, description="Cruise speed (m/s)")
    altitude: float = Field(default=30.0, ge=2, le=500, description="Default altitude (m)")
    waypoints: list[Waypoint] = Field(default_factory=list, max_length=64)

    @field_validator("timeout")
    @classmethod
    def _timeout_duration(cls, value: str) -> str:
        _validate_duration_field(value, field="timeout")
        seconds = parse_duration(value)
        if seconds < 10 or seconds > 3600:
            raise ValueError("timeout must be between 10s and 1h")
        return value

    @property
    def timeout_seconds(self) -> float:
        return parse_duration(self.timeout)


class RecoveryPolicy(StrictModel):
    """Declared recovery behaviour of the target. The adapter maps it to the system.

    These are expectations that the platform will verify, not commands it executes.
    """

    gnss_loss: Literal["dead_reckoning", "hold", "land"] = "dead_reckoning"
    datalink_loss: Literal["continue", "hold", "rtl"] = "continue"
    compute_loss: Literal["hold", "land", "rtl"] = "hold"
    hold_timeout: DurationStr = Field(
        default="60s", description="Maximum time to hold before escalating to land"
    )
    max_dead_reckoning: DurationStr = Field(
        default="90s", description="Maximum time to fly without GNSS aiding before holding"
    )

    @field_validator("hold_timeout", "max_dead_reckoning")
    @classmethod
    def _durations(cls, value: str) -> str:
        return _validate_duration_field(value, field="recovery")


class SimulationConfig(StrictModel):
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    speed: float = Field(default=1.0, ge=0.1, le=100.0, description="Simulation speed factor")
    telemetry_rate_hz: float = Field(default=10.0, ge=1.0, le=50.0)


class Injection(StrictModel):
    subsystem: SubsystemId
    effect: Effect
    duration: DurationStr | None = Field(
        default=None,
        description="How long the effect stays active. Omitted means until scenario end.",
    )
    parameters: dict[Key, ParameterValue | str] = Field(default_factory=dict, max_length=8)

    @field_validator("duration")
    @classmethod
    def _duration(cls, value: str | None) -> str | None:
        if value is not None:
            _validate_duration_field(value, field="duration")
        return value

    @model_validator(mode="after")
    def _check_effect_rules(self) -> Self:
        if self.effect in TRANSIENT_EFFECTS and self.duration is not None:
            raise ValueError(
                f"effect '{self.effect.value}' is transient and does not accept a duration"
            )
        if self.effect in DURATION_REQUIRED_EFFECTS and self.duration is None:
            raise ValueError(f"effect '{self.effect.value}' requires a duration")
        allowed = {p.name: p for p in EFFECT_PARAMETERS.get(self.effect, ())}
        for name, value in self.parameters.items():
            spec = allowed.get(name)
            if spec is None:
                raise ValueError(
                    f"parameter '{name}' is not valid for effect '{self.effect.value}'"
                )
            if spec.type == "duration":
                if not isinstance(value, str):
                    raise ValueError(f"parameter '{name}' must be a duration string")
                _validate_duration_field(value, field=f"parameters.{name}")
            else:
                if isinstance(value, bool) or not isinstance(value, int | float):
                    raise ValueError(f"parameter '{name}' must be numeric")
                if spec.minimum is not None and value < spec.minimum:
                    raise ValueError(f"parameter '{name}' must be >= {spec.minimum}")
                if spec.maximum is not None and value > spec.maximum:
                    raise ValueError(f"parameter '{name}' must be <= {spec.maximum}")
        return self

    @property
    def duration_seconds(self) -> float | None:
        return parse_duration(self.duration) if self.duration else None


class Expectation(StrictModel):
    """Expected observable behaviour after an event. Verified, never assumed."""

    subsystem: SubsystemId
    state: ComponentState
    within: DurationStr = Field(default="5s")
    description: ShortText = ""

    @field_validator("within")
    @classmethod
    def _within(cls, value: str) -> str:
        return _validate_duration_field(value, field="within")

    @property
    def within_seconds(self) -> float:
        return parse_duration(self.within)


class ScenarioEvent(StrictModel):
    id: EventId
    at: DurationStr = Field(description="Simulation time at which the injection is requested")
    inject: Injection
    expect: list[Expectation] = Field(default_factory=list, max_length=8)
    description: ShortText = ""

    @field_validator("at")
    @classmethod
    def _at(cls, value: str) -> str:
        return _validate_duration_field(value, field="at")

    @property
    def at_seconds(self) -> float:
        return parse_duration(self.at)


class Assertion(StrictModel):
    expression: Annotated[str, StringConstraints(min_length=3, max_length=200)]
    severity: Severity = Severity.MEDIUM
    description: ShortText = ""

    @field_validator("expression")
    @classmethod
    def _parse(cls, value: str) -> str:
        try:
            parse_expression(value)
        except ExpressionError as exc:
            raise ValueError(str(exc)) from exc
        return value


class ScoringConfig(StrictModel):
    profile: Slug = Field(default="default", description="Named score profile")


class ConsequenceProfile(StrictModel):
    """Abstract consequence profile (used for electromagnetic resilience scenarios).

    A profile lists the behaviours each subsystem exhibits during a transient. It is
    expanded into ordinary injection events at load time. Subsystems marked
    `operational` are explicitly expected to stay healthy and become expectations.
    No physical source parameter can be expressed here.
    """

    name: Slug
    at: DurationStr = Field(description="Simulation time at which the transient starts")
    duration: DurationStr = Field(description="Transient duration for persistent behaviours")
    effects: dict[SubsystemId, Effect | Literal["operational"]] = Field(min_length=1)
    description: ShortText = ""

    @field_validator("at", "duration")
    @classmethod
    def _durations(cls, value: str) -> str:
        return _validate_duration_field(value, field="profile")


class ResilienceScenario(StrictModel):
    api_version: str = Field(alias="apiVersion")
    kind: str
    metadata: ScenarioMetadata
    target: Target
    mission: Mission = Field(default_factory=Mission)
    recovery: RecoveryPolicy = Field(default_factory=RecoveryPolicy)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    profile: ConsequenceProfile | None = None
    events: list[ScenarioEvent] = Field(default_factory=list, max_length=128)
    assertions: list[Assertion] = Field(default_factory=list, max_length=64)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        frozen=True,
        str_strip_whitespace=True,
        json_schema_extra={
            "title": "ResilienceScenario",
            "$id": "https://resilient-uas.dev/schemas/scenario/v1alpha1.json",
        },
    )

    @field_validator("api_version")
    @classmethod
    def _api_version(cls, value: str) -> str:
        if value not in SUPPORTED_SCENARIO_API_VERSIONS:
            raise ValueError(
                f"unsupported apiVersion {value!r}; supported: "
                f"{', '.join(sorted(SUPPORTED_SCENARIO_API_VERSIONS))}"
            )
        return value

    @field_validator("kind")
    @classmethod
    def _kind(cls, value: str) -> str:
        if value != SCENARIO_KIND:
            raise ValueError(f"unsupported kind {value!r}; expected {SCENARIO_KIND!r}")
        return value

    @model_validator(mode="after")
    def _cross_checks(self) -> Self:
        seen: set[str] = set()
        timeout = self.mission.timeout_seconds
        for index, event in enumerate(self.events):
            if event.id in seen:
                raise ValueError(f"events[{index}]: duplicate event id '{event.id}'")
            seen.add(event.id)
            if event.at_seconds >= timeout:
                raise ValueError(
                    f"events[{index}] '{event.id}': at={event.at} is not before the mission "
                    f"timeout ({self.mission.timeout})"
                )
            if not DEFAULT_CATALOG.topology.has_component(event.inject.subsystem):
                raise ValueError(
                    f"events[{index}] '{event.id}': unknown subsystem '{event.inject.subsystem}'"
                )
            if not DEFAULT_CATALOG.allows(event.inject.subsystem, event.inject.effect):
                allowed = DEFAULT_CATALOG.entry(event.inject.subsystem)
                names = ", ".join(e.value for e in allowed.effects) if allowed else "none"
                raise ValueError(
                    f"events[{index}] '{event.id}': effect '{event.inject.effect.value}' is "
                    f"not allowed for '{event.inject.subsystem}' (allowed: {names})"
                )
            for expectation in event.expect:
                if not DEFAULT_CATALOG.topology.has_component(expectation.subsystem):
                    raise ValueError(
                        f"events[{index}] '{event.id}': expectation references unknown "
                        f"subsystem '{expectation.subsystem}'"
                    )
        if self.profile is not None:
            for subsystem, behaviour in self.profile.effects.items():
                if not DEFAULT_CATALOG.topology.has_component(subsystem):
                    raise ValueError(f"profile.effects: unknown subsystem '{subsystem}'")
                if behaviour != "operational" and not DEFAULT_CATALOG.allows(
                    subsystem, Effect(behaviour)
                ):
                    raise ValueError(
                        f"profile.effects.{subsystem}: effect '{behaviour}' is not allowed"
                    )
        if not self.events and self.profile is None:
            raise ValueError("a scenario needs at least one event or a consequence profile")
        return self

    @property
    def name(self) -> str:
        return self.metadata.name

    def expanded_events(self) -> list[ScenarioEvent]:
        """Return explicit events plus events derived from the consequence profile."""

        events = list(self.events)
        if self.profile is not None:
            profile = self.profile
            operational: list[Expectation] = [
                Expectation(subsystem=subsystem, state=ComponentState.OPERATIONAL, within="1s")
                for subsystem, behaviour in profile.effects.items()
                if behaviour == "operational"
            ]
            first = True
            for subsystem, behaviour in profile.effects.items():
                if behaviour == "operational":
                    continue
                effect = Effect(behaviour)
                duration = None if effect in TRANSIENT_EFFECTS else profile.duration
                event_id = f"{profile.name}-{subsystem.replace('.', '-').replace('_', '-')}"
                events.append(
                    ScenarioEvent(
                        id=event_id,
                        at=profile.at,
                        inject=Injection(subsystem=subsystem, effect=effect, duration=duration),
                        expect=operational if first else [],
                        description=f"Consequence profile '{profile.name}'",
                    )
                )
                first = False
        return sorted(events, key=lambda e: (e.at_seconds, e.id))

    def critical_assertions(self) -> list[Assertion]:
        return [a for a in self.assertions if a.severity is Severity.CRITICAL]

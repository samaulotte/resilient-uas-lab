"""System domain model: components, fault/trust domains, dependencies and boundaries.

The topology is what makes fault-containment analysis possible. Components belong to
a domain; dependencies describe how a fault may propagate; trust boundaries mark the
lines that a fault must not cross (typically between mission compute and the
flight-critical core).

The default topology describes a generic multirotor with a companion computer. It is
adapter-agnostic: the PX4 adapter and the mock adapter both report states for these
component identifiers.
"""

from __future__ import annotations

from collections import deque
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from reslab_core.states import ComponentState


class Domain(StrEnum):
    EXTERNAL = "external"
    COMMUNICATIONS = "communications"
    NAVIGATION = "navigation"
    MISSION_COMPUTE = "mission_compute"
    FLIGHT_CONTROL = "flight_control"
    ACTUATION = "actuation"
    POWER = "power"


DOMAIN_ORDER: tuple[Domain, ...] = (
    Domain.EXTERNAL,
    Domain.COMMUNICATIONS,
    Domain.MISSION_COMPUTE,
    Domain.NAVIGATION,
    Domain.FLIGHT_CONTROL,
    Domain.ACTUATION,
    Domain.POWER,
)

# Domains whose impairment constitutes loss of the flight-critical function.
CRITICAL_DOMAINS: frozenset[Domain] = frozenset({Domain.FLIGHT_CONTROL, Domain.ACTUATION})


class FaultCategory(StrEnum):
    """Fault library categories exposed to scenario authors."""

    NAVIGATION = "Navigation"
    SENSORS = "Sensors"
    COMMUNICATIONS = "Communications"
    COMPUTE = "Compute"
    PROCESS = "Process"
    NETWORK = "Network"
    POWER = "Power"
    SECURITY_BOUNDARY = "Security boundary"
    SERVICE = "Service"


class TrustZone(StrEnum):
    """Trust zones, ordered from least to most trusted."""

    EXTERNAL = "external"
    MISSION = "mission"
    FLIGHT_CRITICAL = "flight_critical"


class Component(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Subsystem identifier '<category>.<component>'")
    name: str
    domain: Domain
    category: FaultCategory
    trust_zone: TrustZone
    healthy_state: ComponentState = Field(
        default=ComponentState.NOMINAL,
        description="Vocabulary used when the component is healthy (NOMINAL or OPERATIONAL)",
    )
    critical: bool = Field(
        default=False, description="Loss of this component means loss of flight-critical function"
    )
    description: str = ""


class Dependency(BaseModel):
    """`dependent` relies on `provider`; a fault on the provider may propagate downstream."""

    model_config = ConfigDict(frozen=True)

    provider: str
    dependent: str
    relation: str = Field(default="depends_on")
    crosses_trust_boundary: bool = False


class TrustBoundary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    upstream_zone: TrustZone
    downstream_zone: TrustZone
    enforcement_point: str | None = Field(
        default=None, description="Component id acting as policy enforcement point"
    )
    description: str = ""


class SystemTopology(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    vehicle_class: str
    components: tuple[Component, ...]
    dependencies: tuple[Dependency, ...]
    trust_boundaries: tuple[TrustBoundary, ...]

    def component(self, component_id: str) -> Component:
        for component in self.components:
            if component.id == component_id:
                return component
        raise KeyError(component_id)

    def has_component(self, component_id: str) -> bool:
        return any(c.id == component_id for c in self.components)

    @property
    def component_ids(self) -> tuple[str, ...]:
        return tuple(c.id for c in self.components)

    @property
    def critical_component_ids(self) -> frozenset[str]:
        return frozenset(c.id for c in self.components if c.critical)

    def domain_of(self, component_id: str) -> Domain:
        return self.component(component_id).domain

    def downstream(self, component_id: str) -> tuple[str, ...]:
        return tuple(d.dependent for d in self.dependencies if d.provider == component_id)

    def upstream(self, component_id: str) -> tuple[str, ...]:
        return tuple(d.provider for d in self.dependencies if d.dependent == component_id)

    def propagation_depths(self, origins: set[str], affected: set[str]) -> dict[str, int]:
        """Shortest dependency distance from any origin to each affected component.

        Only edges whose both ends are affected are followed: a healthy component
        stops propagation. Origins have depth 0. Affected components unreachable
        from an origin through affected components get depth -1 (independent fault).
        """

        depths: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque()
        for origin in origins:
            if origin in affected:
                depths[origin] = 0
                queue.append((origin, 0))
        while queue:
            current, depth = queue.popleft()
            for nxt in self.downstream(current):
                if nxt in affected and nxt not in depths:
                    depths[nxt] = depth + 1
                    queue.append((nxt, depth + 1))
        for component_id in affected:
            depths.setdefault(component_id, -1)
        return depths

    def healthy_state_for(self, component_id: str) -> ComponentState:
        return self.component(component_id).healthy_state


def default_multirotor_topology() -> SystemTopology:
    """Generic multirotor with companion computer and a mission/flight trust boundary."""

    ns = ComponentState.NOMINAL
    op = ComponentState.OPERATIONAL
    components = (
        Component(
            id="external.gcs",
            name="Ground Control Station",
            domain=Domain.EXTERNAL,
            category=FaultCategory.SERVICE,
            trust_zone=TrustZone.EXTERNAL,
            healthy_state=ns,
            description="Operator ground station issuing commands over the C2 link.",
        ),
        Component(
            id="communications.c2",
            name="C2 Datalink",
            domain=Domain.COMMUNICATIONS,
            category=FaultCategory.COMMUNICATIONS,
            trust_zone=TrustZone.EXTERNAL,
            healthy_state=ns,
            description="Command and control link between the ground station and the vehicle.",
        ),
        Component(
            id="communications.telemetry",
            name="Telemetry Gateway",
            domain=Domain.COMMUNICATIONS,
            category=FaultCategory.COMMUNICATIONS,
            trust_zone=TrustZone.MISSION,
            healthy_state=ns,
            description="Onboard gateway forwarding telemetry to the ground and commands onboard.",
        ),
        Component(
            id="mission.compute",
            name="Mission Computer",
            domain=Domain.MISSION_COMPUTE,
            category=FaultCategory.COMPUTE,
            trust_zone=TrustZone.MISSION,
            healthy_state=op,
            description="Companion computer hosting mission planning and autonomy services.",
        ),
        Component(
            id="mission.planner",
            name="Mission Planner Process",
            domain=Domain.MISSION_COMPUTE,
            category=FaultCategory.PROCESS,
            trust_zone=TrustZone.MISSION,
            healthy_state=op,
            description="Process sequencing waypoints and issuing setpoints to the flight core.",
        ),
        Component(
            id="mission.services",
            name="Mission Services",
            domain=Domain.MISSION_COMPUTE,
            category=FaultCategory.SERVICE,
            trust_zone=TrustZone.MISSION,
            healthy_state=ns,
            description="Auxiliary onboard services (payload, logging, perception).",
        ),
        Component(
            id="network.companion_link",
            name="Companion Link",
            domain=Domain.MISSION_COMPUTE,
            category=FaultCategory.NETWORK,
            trust_zone=TrustZone.MISSION,
            healthy_state=ns,
            description="Onboard network link between the mission computer and the flight core.",
        ),
        Component(
            id="security.gateway",
            name="Command Gateway",
            domain=Domain.FLIGHT_CONTROL,
            category=FaultCategory.SECURITY_BOUNDARY,
            trust_zone=TrustZone.FLIGHT_CRITICAL,
            healthy_state=op,
            description=(
                "Policy enforcement point validating mission commands before they reach "
                "the flight core. Fails closed."
            ),
        ),
        Component(
            id="navigation.gnss",
            name="GNSS Receiver",
            domain=Domain.NAVIGATION,
            category=FaultCategory.NAVIGATION,
            trust_zone=TrustZone.FLIGHT_CRITICAL,
            healthy_state=ns,
            description="Satellite positioning source used to aid the navigation estimator.",
        ),
        Component(
            id="navigation.estimator",
            name="Navigation Estimator",
            domain=Domain.NAVIGATION,
            category=FaultCategory.NAVIGATION,
            trust_zone=TrustZone.FLIGHT_CRITICAL,
            healthy_state=ns,
            description="State estimator fusing GNSS, inertial, barometric and magnetic data.",
        ),
        Component(
            id="sensors.barometer",
            name="Barometer",
            domain=Domain.NAVIGATION,
            category=FaultCategory.SENSORS,
            trust_zone=TrustZone.FLIGHT_CRITICAL,
            healthy_state=ns,
        ),
        Component(
            id="sensors.magnetometer",
            name="Magnetometer",
            domain=Domain.NAVIGATION,
            category=FaultCategory.SENSORS,
            trust_zone=TrustZone.FLIGHT_CRITICAL,
            healthy_state=ns,
        ),
        Component(
            id="sensors.imu",
            name="Inertial Measurement Unit",
            domain=Domain.FLIGHT_CONTROL,
            category=FaultCategory.SENSORS,
            trust_zone=TrustZone.FLIGHT_CRITICAL,
            healthy_state=ns,
            critical=True,
            description="Primary attitude sensing for the flight core.",
        ),
        Component(
            id="flight_control.core",
            name="Flight Core",
            domain=Domain.FLIGHT_CONTROL,
            category=FaultCategory.COMPUTE,
            trust_zone=TrustZone.FLIGHT_CRITICAL,
            healthy_state=op,
            critical=True,
            description="Flight controller running attitude and position control loops.",
        ),
        Component(
            id="actuation.motors",
            name="Motors and ESCs",
            domain=Domain.ACTUATION,
            category=FaultCategory.POWER,
            trust_zone=TrustZone.FLIGHT_CRITICAL,
            healthy_state=op,
            critical=True,
        ),
        Component(
            id="power.battery",
            name="Battery",
            domain=Domain.POWER,
            category=FaultCategory.POWER,
            trust_zone=TrustZone.FLIGHT_CRITICAL,
            healthy_state=ns,
        ),
        Component(
            id="power.bus",
            name="Power Distribution",
            domain=Domain.POWER,
            category=FaultCategory.POWER,
            trust_zone=TrustZone.FLIGHT_CRITICAL,
            healthy_state=ns,
        ),
    )
    dependencies = (
        Dependency(provider="external.gcs", dependent="communications.c2", relation="commands"),
        Dependency(provider="communications.c2", dependent="communications.telemetry"),
        Dependency(provider="communications.telemetry", dependent="mission.compute"),
        Dependency(provider="mission.compute", dependent="mission.planner", relation="hosts"),
        Dependency(provider="mission.compute", dependent="mission.services", relation="hosts"),
        Dependency(provider="mission.planner", dependent="network.companion_link"),
        Dependency(
            provider="network.companion_link",
            dependent="security.gateway",
            crosses_trust_boundary=True,
        ),
        Dependency(
            provider="security.gateway", dependent="flight_control.core", relation="commands"
        ),
        Dependency(provider="navigation.gnss", dependent="navigation.estimator", relation="aids"),
        Dependency(provider="sensors.barometer", dependent="navigation.estimator", relation="aids"),
        Dependency(
            provider="sensors.magnetometer", dependent="navigation.estimator", relation="aids"
        ),
        Dependency(provider="sensors.imu", dependent="navigation.estimator", relation="aids"),
        Dependency(provider="sensors.imu", dependent="flight_control.core", relation="aids"),
        Dependency(
            provider="navigation.estimator", dependent="flight_control.core", relation="aids"
        ),
        Dependency(provider="navigation.estimator", dependent="mission.planner", relation="aids"),
        Dependency(provider="flight_control.core", dependent="actuation.motors", relation="drives"),
        Dependency(provider="power.battery", dependent="power.bus", relation="supplies"),
        Dependency(provider="power.bus", dependent="actuation.motors", relation="supplies"),
        Dependency(provider="power.bus", dependent="flight_control.core", relation="supplies"),
        Dependency(provider="power.bus", dependent="mission.compute", relation="supplies"),
    )
    boundaries = (
        TrustBoundary(
            id="mission-flight",
            name="Mission / Flight-critical boundary",
            upstream_zone=TrustZone.MISSION,
            downstream_zone=TrustZone.FLIGHT_CRITICAL,
            enforcement_point="security.gateway",
            description=(
                "Commands from the mission computer are validated by the command gateway "
                "before reaching the flight core. The flight core keeps full control "
                "authority if everything upstream fails."
            ),
        ),
        TrustBoundary(
            id="external-mission",
            name="External / Mission boundary",
            upstream_zone=TrustZone.EXTERNAL,
            downstream_zone=TrustZone.MISSION,
            enforcement_point="communications.telemetry",
            description="Ground commands enter the vehicle through the telemetry gateway.",
        ),
    )
    return SystemTopology(
        id="multirotor-companion-v1",
        name="Multirotor with companion computer",
        vehicle_class="multirotor",
        components=components,
        dependencies=dependencies,
        trust_boundaries=boundaries,
    )


DEFAULT_TOPOLOGY = default_multirotor_topology()

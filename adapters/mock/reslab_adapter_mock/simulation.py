"""Deterministic step-based simulation of a multirotor with a companion computer.

The model is intentionally simple and fully documented so that engineers can reason
about every number the mock produces:

- kinematics: first-order velocity response towards the active target, bounded
  acceleration, cruise speed scaled by degradation factors;
- navigation: GNSS-aided estimator or dead reckoning with seeded drift;
- component states: derived from active effects and dependency propagation;
- failsafes: hold / return / land decided by the declared recovery policy.

All randomness comes from `random.Random(seed)`. Two runs with the same seed, scenario
and speed produce identical telemetry.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from reslab_core.adapter import (
    ClearRequest,
    InjectionRequest,
    InjectionResult,
    MissionEvent,
    Observation,
    SystemResponse,
)
from reslab_core.duration import parse_duration
from reslab_core.scenario.catalog import Effect
from reslab_core.scenario.model import Mission, RecoveryPolicy
from reslab_core.states import ComponentState, FlightMode, MissionPhase
from reslab_core.telemetry import (
    Attitude,
    CommunicationsStatus,
    ComponentStateChange,
    FlightStatus,
    GeoPosition,
    MissionStatus,
    NavigationStatus,
    PlannedPath,
    Position,
    PowerStatus,
    TelemetrySample,
    Velocity,
    utcnow,
)
from reslab_core.topology import DEFAULT_TOPOLOGY, SystemTopology

NOMINAL = ComponentState.NOMINAL
OPERATIONAL = ComponentState.OPERATIONAL
DEGRADED = ComponentState.DEGRADED
UNAVAILABLE = ComponentState.UNAVAILABLE
FAILED = ComponentState.FAILED
RECOVERING = ComponentState.RECOVERING
RECOVERED = ComponentState.RECOVERED

EARTH_RADIUS = 6371000.0


@dataclass
class ActiveEffect:
    event_id: str
    subsystem: str
    effect: Effect
    started_at: float
    duration: float | None
    parameters: dict[str, float | int | str]
    stage: str = "active"
    stage_until: float | None = None

    def param(self, name: str, default: float) -> float:
        value = self.parameters.get(name)
        if value is None:
            return default
        if isinstance(value, str):
            return parse_duration(value)
        return float(value)


@dataclass
class _Derived:
    """Component states and behavioural factors derived for one step."""

    states: dict[str, ComponentState]
    causes: dict[str, str]
    reasons: dict[str, str]
    speed_factor: float = 1.0
    commands_available: bool = True
    command_loss_reason: str = ""
    gnss_aiding: bool = True
    control_lost: bool = False
    attitude_noise: float = 0.0
    latency_ms: float = 0.0
    packet_loss: float = 0.0
    c2_link: bool = True
    telemetry_link: bool = True
    battery_factor: float = 1.0


@dataclass
class MockSimulation:
    seed: int
    mission: Mission
    recovery: RecoveryPolicy
    planned_path: PlannedPath
    rate_hz: float = 10.0
    topology: SystemTopology = DEFAULT_TOPOLOGY
    source: str = "mock"

    t: float = 0.0
    armed: bool = False
    finished: bool = False
    mode: FlightMode = FlightMode.IDLE
    phase: MissionPhase = MissionPhase.PENDING
    position: Position = field(default_factory=lambda: Position(x=0.0, y=0.0, z=0.0))
    velocity: Velocity = field(default_factory=lambda: Velocity(vx=0.0, vy=0.0, vz=0.0))
    attitude: Attitude = field(default_factory=lambda: Attitude(roll=0.0, pitch=0.0, yaw=0.0))
    waypoint_index: int = 1
    effects: dict[str, ActiveEffect] = field(default_factory=dict)
    previous_states: dict[str, ComponentState] = field(default_factory=dict)
    recovered_marks: set[str] = field(default_factory=set)
    log: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)  # noqa: S311 - deterministic simulation, not security
        self.dt = 1.0 / self.rate_hz
        self.waypoints = list(self.planned_path.waypoints)
        self._estimate = Position(x=0.0, y=0.0, z=0.0)
        self._drift = (0.0, 0.0)
        self._unaided_since: float | None = None
        self._hold_since: float | None = None
        self._hold_reason = ""
        self._land_reason = ""
        self._rtl_reason = ""
        self._autonomy = "mission"
        self._last_commands_available = True
        self._last_c2 = True
        self._battery = 1.0
        self._voltage = 16.8
        self._legs_total = max(len(self.waypoints) - 1, 1) + 1  # +1 for landing
        self._gust = (0.0, 0.0)
        self._pending_responses: list[SystemResponse] = []
        self._pending_mission_events: list[MissionEvent] = []
        self._brownout_until: float | None = None
        self._planner_watchdog_until: float | None = None
        self.previous_states = self._healthy_states()

    # ------------------------------------------------------------------ public API

    def start(self) -> None:
        self.armed = True
        self.mode = FlightMode.TAKEOFF
        self.phase = MissionPhase.TAKEOFF
        self.log.append(f"{self.t:.1f}s armed, takeoff")

    def inject(self, request: InjectionRequest) -> InjectionResult:
        if not self.topology.has_component(request.subsystem):
            return InjectionResult(
                applied=False, mechanism="mock", detail=f"unknown subsystem {request.subsystem}"
            )
        effect = ActiveEffect(
            event_id=request.scenario_event_id,
            subsystem=request.subsystem,
            effect=request.effect,
            started_at=self.t,
            duration=request.duration,
            parameters=dict(request.parameters),
        )
        if request.effect is Effect.RESTART:
            restart_time = effect.param("restart_time", self.rng.uniform(3.6, 5.2))
            effect.stage = "restarting"
            effect.stage_until = self.t + restart_time
        elif request.effect is Effect.CRASH:
            watchdog = effect.param("watchdog_time", self.rng.uniform(1.5, 2.5))
            effect.stage = "crashed"
            effect.stage_until = self.t + watchdog
        self.effects[request.scenario_event_id] = effect
        self.log.append(
            f"{self.t:.1f}s inject {request.effect.value} -> {request.subsystem} "
            f"({request.scenario_event_id})"
        )
        return InjectionResult(
            applied=True,
            mechanism="mock:component-state-model",
            detail=f"{request.effect.value} active on {request.subsystem}",
        )

    def clear(self, request: ClearRequest) -> InjectionResult:
        effect = self.effects.pop(request.scenario_event_id, None)
        if effect is None:
            return InjectionResult(applied=False, mechanism="mock", detail="effect not active")
        self.log.append(f"{self.t:.1f}s clear {effect.effect.value} on {effect.subsystem}")
        return InjectionResult(applied=True, mechanism="mock:component-state-model")

    def health(self) -> dict[str, ComponentState]:
        return dict(self.previous_states)

    # ------------------------------------------------------------------ helpers

    def _healthy_states(self) -> dict[str, ComponentState]:
        return {c.id: c.healthy_state for c in self.topology.components}

    def _effects_on(self, subsystem: str) -> list[ActiveEffect]:
        return [e for e in self.effects.values() if e.subsystem == subsystem]

    def _advance_transients(self) -> None:
        for effect in list(self.effects.values()):
            if effect.effect is Effect.CRASH and effect.stage == "crashed":
                if effect.stage_until is not None and self.t >= effect.stage_until:
                    effect.stage = "restarting"
                    effect.stage_until = self.t + effect.param(
                        "restart_time", self.rng.uniform(3.8, 5.4)
                    )
            if effect.stage == "restarting" and effect.stage_until is not None:
                if self.t >= effect.stage_until:
                    del self.effects[effect.event_id]
                    self.recovered_marks.add(effect.subsystem)
                    self.log.append(f"{self.t:.1f}s {effect.subsystem} restarted")

    def _intermittent_available(self, effect: ActiveEffect) -> bool:
        period = effect.param("period", 2.0)
        duty = effect.param("duty_cycle", 0.4)
        phase = ((self.t - effect.started_at) % period) / period
        return phase < duty

    # ------------------------------------------------------------------ derivation

    def _derive(self) -> _Derived:
        states = self._healthy_states()
        for subsystem in self.recovered_marks:
            states[subsystem] = RECOVERED
        d = _Derived(states=states, causes={}, reasons={})

        def set_state(subsystem: str, state: ComponentState, cause: str, reason: str) -> None:
            current = d.states[subsystem]
            rank = {
                RECOVERED: 0,
                NOMINAL: 0,
                OPERATIONAL: 0,
                DEGRADED: 1,
                UNAVAILABLE: 2,
                RECOVERING: 2,
                FAILED: 3,
            }
            if rank[state] >= rank[current]:
                d.states[subsystem] = state
                d.causes[subsystem] = cause
                d.reasons[subsystem] = reason

        # ---- direct effects
        for e in self.effects.values():
            s = e.subsystem
            match e.effect:
                case Effect.UNAVAILABLE:
                    set_state(s, UNAVAILABLE, e.event_id, "injected unavailable")
                case Effect.TEMPORARY_DISCONNECT:
                    set_state(s, UNAVAILABLE, e.event_id, "temporary disconnect")
                case Effect.INTERMITTENT:
                    if not self._intermittent_available(e):
                        set_state(s, UNAVAILABLE, e.event_id, "intermittent: off phase")
                    else:
                        set_state(s, DEGRADED, e.event_id, "intermittent: on phase")
                case Effect.DEGRADED:
                    set_state(s, DEGRADED, e.event_id, "injected degradation")
                case Effect.ERRONEOUS:
                    set_state(s, DEGRADED, e.event_id, "erroneous output")
                case Effect.STUCK:
                    set_state(s, DEGRADED, e.event_id, "stuck output")
                case Effect.LATENCY:
                    set_state(s, DEGRADED, e.event_id, "added latency")
                    d.latency_ms = max(d.latency_ms, e.param("latency_ms", 400.0))
                case Effect.PACKET_LOSS:
                    set_state(s, DEGRADED, e.event_id, "packet loss")
                    d.packet_loss = max(d.packet_loss, e.param("loss_ratio", 0.3))
                case Effect.RESOURCE_PRESSURE:
                    set_state(s, DEGRADED, e.event_id, "resource pressure")
                case Effect.RESTART:
                    set_state(s, RECOVERING, e.event_id, "restarting")
                case Effect.CRASH:
                    if e.stage == "crashed":
                        set_state(s, FAILED, e.event_id, "process crashed")
                    else:
                        set_state(s, RECOVERING, e.event_id, "restarting after crash")

        # ---- sensor / navigation propagation
        gnss = d.states["navigation.gnss"]
        gnss_effects = self._effects_on("navigation.gnss")
        gnss_usable = gnss.is_healthy
        for e in gnss_effects:
            # Erroneous and stuck outputs are detected by the estimator's consistency
            # checks after a short delay, after which GNSS is rejected as an aid.
            if e.effect in (Effect.ERRONEOUS, Effect.STUCK) and self.t - e.started_at > 1.0:
                gnss_usable = False
            if e.effect is Effect.DEGRADED:
                gnss_usable = True
        if gnss in (UNAVAILABLE, FAILED, RECOVERING):
            gnss_usable = False
        d.gnss_aiding = gnss_usable
        if not gnss_usable:
            cause = d.causes.get("navigation.gnss", "")
            set_state("navigation.estimator", DEGRADED, cause, "dead reckoning: GNSS aiding lost")
        elif gnss is DEGRADED:
            cause = d.causes.get("navigation.gnss", "")
            set_state("navigation.estimator", DEGRADED, cause, "degraded GNSS aiding")
        for sensor in ("sensors.barometer", "sensors.magnetometer"):
            if not d.states[sensor].is_healthy:
                set_state(
                    "navigation.estimator",
                    DEGRADED,
                    d.causes.get(sensor, ""),
                    f"{sensor.split('.')[1]} rejected by estimator",
                )
        if not d.states["sensors.imu"].is_healthy:
            set_state(
                "flight_control.core",
                DEGRADED,
                d.causes.get("sensors.imu", ""),
                "attitude estimate degraded",
            )
            d.attitude_noise = max(d.attitude_noise, 0.04)

        # ---- power propagation
        battery = d.states["power.battery"]
        if battery is DEGRADED:
            level = 1.0
            for e in self._effects_on("power.battery"):
                if e.effect is Effect.DEGRADED:
                    level = min(level, e.param("level", 0.7))
            d.battery_factor = max(0.3, level)
        bus = d.states["power.bus"]
        if bus in (DEGRADED, UNAVAILABLE):
            level = 1.0
            for e in self._effects_on("power.bus"):
                if e.effect is Effect.DEGRADED:
                    level = min(level, e.param("level", 0.6))
            if level < 0.5 or bus is UNAVAILABLE:
                # Transient power degradation causes a companion brownout.
                if self._brownout_until is None:
                    self._brownout_until = self.t + self.rng.uniform(3.0, 4.5)
                    self.log.append(f"{self.t:.1f}s companion brownout")
        if self._brownout_until is not None:
            if self.t < self._brownout_until:
                set_state(
                    "mission.compute", RECOVERING, d.causes.get("power.bus", ""), "brownout restart"
                )
            else:
                self._brownout_until = None
                self.recovered_marks.add("mission.compute")

        # ---- compute / process propagation
        compute = d.states["mission.compute"]
        if compute.is_down:
            set_state(
                "mission.planner", UNAVAILABLE, d.causes.get("mission.compute", ""), "host down"
            )
            set_state(
                "mission.services", UNAVAILABLE, d.causes.get("mission.compute", ""), "host down"
            )
        elif compute is DEGRADED:
            load = 0.6
            for e in self._effects_on("mission.compute"):
                if e.effect is Effect.RESOURCE_PRESSURE:
                    load = max(load, e.param("load", 0.7))
                if e.effect is Effect.DEGRADED:
                    load = max(load, 1.0 - e.param("level", 0.5))
            set_state(
                "mission.planner",
                DEGRADED,
                d.causes.get("mission.compute", ""),
                "reduced planning rate",
            )
            d.speed_factor = min(d.speed_factor, max(0.35, 1.0 - 0.6 * load))
        planner = d.states["mission.planner"]
        if planner is DEGRADED and compute.is_healthy:
            d.speed_factor = min(d.speed_factor, 0.7)

        # ---- command path: planner -> companion link -> command gateway -> flight core
        link = d.states["network.companion_link"]
        gateway = d.states["security.gateway"]
        if planner.is_down:
            d.commands_available = False
            d.command_loss_reason = "mission planner unavailable"
        elif link.is_down:
            d.commands_available = False
            d.command_loss_reason = "companion link down"
        elif gateway.is_down:
            d.commands_available = False
            d.command_loss_reason = "command gateway unavailable (fail-closed)"
        if link is DEGRADED or gateway is DEGRADED:
            d.speed_factor = min(d.speed_factor, 0.85)

        # ---- communications
        c2 = d.states["communications.c2"]
        gcs = d.states["external.gcs"]
        if not gcs.is_healthy:
            set_state(
                "communications.c2",
                DEGRADED,
                d.causes.get("external.gcs", ""),
                "ground station unavailable",
            )
            c2 = d.states["communications.c2"]
        d.c2_link = not c2.is_down and gcs.is_healthy
        tel = d.states["communications.telemetry"]
        d.telemetry_link = not tel.is_down

        # ---- flight control
        fc = d.states["flight_control.core"]
        if fc is RECOVERING or fc is FAILED:
            d.control_lost = True
        elif fc is DEGRADED:
            d.attitude_noise = max(d.attitude_noise, 0.03)
            d.speed_factor = min(d.speed_factor, 0.8)
        motors = d.states["actuation.motors"]
        if motors is DEGRADED:
            d.speed_factor = min(d.speed_factor, 0.75)
            d.attitude_noise = max(d.attitude_noise, 0.02)
        elif motors.is_down:
            d.control_lost = True
        d.speed_factor = min(d.speed_factor, 0.6 + 0.4 * d.battery_factor)
        if not d.gnss_aiding:
            d.speed_factor = min(d.speed_factor, 0.85)
        return d

    # ------------------------------------------------------------------ decisions

    def _decide_mode(self, d: _Derived) -> None:
        """Apply the recovery policy and failsafes. Priority: LAND > RTL > HOLD > MISSION."""

        if self.phase in (MissionPhase.COMPLETE, MissionPhase.ABORTED):
            return
        if d.control_lost:
            if self.phase is not MissionPhase.ABORTED:
                self._pending_responses.append(
                    SystemResponse(
                        response_type="loss_of_control",
                        message="Flight core lost control authority",
                        subsystem="flight_control.core",
                        safe_state=False,
                    )
                )
            self.phase = MissionPhase.ABORTED
            self.mode = FlightMode.UNKNOWN
            self.finished = True
            return

        wants_hold = False
        hold_reason = ""
        wants_rtl = False
        rtl_reason = ""
        wants_land = False
        land_reason = ""

        # Mission command path
        if not d.commands_available:
            if self.recovery.compute_loss == "hold":
                wants_hold, hold_reason = True, d.command_loss_reason
            elif self.recovery.compute_loss == "rtl":
                wants_rtl, rtl_reason = True, d.command_loss_reason
            else:
                wants_land, land_reason = True, d.command_loss_reason
        # GNSS aiding
        if not d.gnss_aiding:
            if self._unaided_since is None:
                self._unaided_since = self.t
            unaided_for = self.t - self._unaided_since
            policy = self.recovery.gnss_loss
            max_dr = parse_duration(self.recovery.max_dead_reckoning)
            if policy == "hold" or (policy == "dead_reckoning" and unaided_for > max_dr):
                wants_hold, hold_reason = True, "navigation without GNSS aiding"
            elif policy == "land":
                wants_land, land_reason = True, "GNSS aiding lost"
        else:
            self._unaided_since = None
        # Datalink
        if not d.c2_link:
            policy = self.recovery.datalink_loss
            if policy == "hold":
                wants_hold, hold_reason = True, "C2 link lost"
            elif policy == "rtl":
                wants_rtl, rtl_reason = True, "C2 link lost"
        # Battery
        if d.battery_factor < 0.4 or self._battery < 0.15:
            wants_rtl, rtl_reason = True, "low battery"

        # Hold escalation
        if wants_hold:
            if self._hold_since is None:
                self._hold_since = self.t
            elif self.t - self._hold_since > parse_duration(self.recovery.hold_timeout):
                wants_land, land_reason = True, f"hold timeout ({hold_reason})"
        else:
            self._hold_since = None

        previous_mode = self.mode
        if self.phase is MissionPhase.TAKEOFF and not wants_land:
            # Takeoff continues under hold requests; the vehicle reaches a safe altitude first.
            self.mode = FlightMode.TAKEOFF
        elif wants_land:
            self.mode = FlightMode.LAND
            self.phase = MissionPhase.LANDING
            self._land_reason = land_reason
        elif wants_rtl:
            self.mode = FlightMode.RTL
            self.phase = MissionPhase.RETURNING
            self._rtl_reason = rtl_reason
        elif wants_hold:
            self.mode = FlightMode.HOLD
            self.phase = MissionPhase.HOLDING
            self._hold_reason = hold_reason
        else:
            if self.phase is MissionPhase.HOLDING:
                self.phase = MissionPhase.ENROUTE
            if self.phase in (MissionPhase.ENROUTE, MissionPhase.RETURNING):
                self.mode = FlightMode.MISSION
            if self.phase is MissionPhase.LANDING:
                self.mode = FlightMode.LAND

        # Autonomy attribution
        autonomy = "mission"
        if self.mode in (FlightMode.HOLD, FlightMode.RTL) or (
            self.mode is FlightMode.LAND and self._land_reason
        ):
            autonomy = "failsafe"
        elif not d.c2_link:
            autonomy = "local"
        if autonomy != self._autonomy:
            if autonomy == "local":
                self._pending_responses.append(
                    SystemResponse(
                        response_type="local_autonomy_active",
                        message="Local autonomy active: mission continues without C2 link",
                        subsystem="mission.compute",
                        safe_state=False,
                    )
                )
            elif autonomy == "mission" and self._autonomy == "local":
                self._pending_responses.append(
                    SystemResponse(
                        response_type="c2_authority_restored",
                        message="C2 link restored: ground supervision resumed",
                        subsystem="communications.c2",
                    )
                )
            self._autonomy = autonomy

        if self.mode != previous_mode:
            if self.mode is FlightMode.HOLD:
                self._pending_responses.append(
                    SystemResponse(
                        response_type="failsafe_hold",
                        message=f"Flight core entered HOLD: {hold_reason}",
                        subsystem="flight_control.core",
                        safe_state=True,
                    )
                )
            elif self.mode is FlightMode.RTL:
                self._pending_responses.append(
                    SystemResponse(
                        response_type="failsafe_rtl",
                        message=f"Return to launch: {rtl_reason}",
                        subsystem="flight_control.core",
                        safe_state=True,
                    )
                )
            elif (
                self.mode is FlightMode.LAND
                and self._land_reason
                and (previous_mode is not FlightMode.LAND)
            ):
                self._pending_responses.append(
                    SystemResponse(
                        response_type="failsafe_land",
                        message=f"Landing: {land_reason}",
                        subsystem="flight_control.core",
                        safe_state=True,
                    )
                )
            elif self.mode is FlightMode.MISSION and previous_mode is FlightMode.HOLD:
                self._pending_responses.append(
                    SystemResponse(
                        response_type="mission_resumed",
                        message="Mission resumed after hold",
                        subsystem="mission.planner",
                    )
                )

    # ------------------------------------------------------------------ motion

    def _target(self) -> Position | None:
        if self.mode is FlightMode.TAKEOFF:
            return Position(x=0.0, y=0.0, z=self.mission.altitude)
        if self.mode is FlightMode.MISSION:
            if self.phase is MissionPhase.RETURNING:
                return Position(x=0.0, y=0.0, z=self.waypoints[-1].z)
            if self.waypoint_index < len(self.waypoints):
                wp = self.waypoints[self.waypoint_index]
                # With GNSS lost the planner steers towards its (drifting) estimate of the
                # waypoint, so the true path deviates by the estimation error.
                dx = self.position.x - self._estimate.x
                dy = self.position.y - self._estimate.y
                return Position(x=wp.x + dx, y=wp.y + dy, z=wp.z)
        if self.mode is FlightMode.RTL:
            return Position(x=0.0, y=0.0, z=max(self.position.z, self.mission.altitude))
        if self.mode is FlightMode.LAND:
            return Position(x=self.position.x, y=self.position.y, z=0.0)
        return None

    def _move(self, d: _Derived) -> None:
        dt = self.dt
        target = self._target()
        max_speed = self.mission.cruise_speed * d.speed_factor
        climb_rate = 2.5
        descent_rate = 1.5
        accel = 2.5
        desired = Velocity(vx=0.0, vy=0.0, vz=0.0)
        if target is not None and self.mode is not FlightMode.HOLD:
            dx, dy, dz = (
                target.x - self.position.x,
                target.y - self.position.y,
                target.z - self.position.z,
            )
            dist_h = math.hypot(dx, dy)
            if self.mode in (FlightMode.TAKEOFF,):
                desired = Velocity(vx=0.0, vy=0.0, vz=max(-descent_rate, min(climb_rate, dz)))
            elif self.mode is FlightMode.LAND:
                desired = Velocity(
                    vx=0.0, vy=0.0, vz=-descent_rate if self.position.z > 0.05 else 0.0
                )
            else:
                speed = min(max_speed, max(0.6, dist_h))  # slow down near the target
                if dist_h > 1e-6:
                    desired = Velocity(
                        vx=dx / dist_h * speed,
                        vy=dy / dist_h * speed,
                        vz=max(-descent_rate, min(climb_rate, dz)),
                    )
        # Seeded, slowly varying gust so paths are never perfectly straight.
        gx = 0.92 * self._gust[0] + self.rng.gauss(0.0, 0.08)
        gy = 0.92 * self._gust[1] + self.rng.gauss(0.0, 0.08)
        self._gust = (gx, gy)
        ax = max(-accel, min(accel, (desired.vx + gx - self.velocity.vx) / max(dt, 1e-3)))
        ay = max(-accel, min(accel, (desired.vy + gy - self.velocity.vy) / max(dt, 1e-3)))
        az = max(-accel, min(accel, (desired.vz - self.velocity.vz) / max(dt, 1e-3)))
        vx = self.velocity.vx + ax * dt
        vy = self.velocity.vy + ay * dt
        vz = self.velocity.vz + az * dt
        if self.mode is FlightMode.HOLD:
            vx *= 0.7
            vy *= 0.7
            vz *= 0.7
        x = self.position.x + vx * dt
        y = self.position.y + vy * dt
        z = max(0.0, self.position.z + vz * dt)
        self.velocity = Velocity(vx=vx, vy=vy, vz=vz)
        self.position = Position(x=x, y=y, z=z)

        speed_h = math.hypot(vx, vy)
        yaw = self.attitude.yaw if speed_h < 0.3 else math.atan2(vx, vy)
        pitch = -math.atan2(ax * 0.12, 9.81) * 2.5
        roll = math.atan2(ay * 0.12, 9.81) * 2.5
        noise = d.attitude_noise
        if noise > 0:
            roll += self.rng.gauss(0.0, noise)
            pitch += self.rng.gauss(0.0, noise)
        self.attitude = Attitude(roll=roll, pitch=pitch, yaw=yaw)

        # Battery: 15 minutes nominal endurance, faster drain when degraded.
        drain = (
            dt / (15 * 60) * (1.0 if self.position.z > 0.1 else 0.2) / max(0.3, d.battery_factor)
        )
        self._battery = max(0.0, self._battery - drain)
        self._voltage = 14.0 + 2.8 * self._battery * (0.85 + 0.15 * d.battery_factor)

    def _update_estimate(self, d: _Derived) -> None:
        if d.gnss_aiding:
            self._estimate = Position(
                x=self.position.x + self.rng.gauss(0.0, 0.3),
                y=self.position.y + self.rng.gauss(0.0, 0.3),
                z=self.position.z + self.rng.gauss(0.0, 0.2),
            )
            self._drift = (0.0, 0.0)
        else:
            # Dead reckoning: integrate velocity with a slowly wandering bias.
            bx = 0.98 * self._drift[0] + self.rng.gauss(0.0, 0.02)
            by = 0.98 * self._drift[1] + self.rng.gauss(0.0, 0.02)
            self._drift = (bx, by)
            self._estimate = Position(
                x=self._estimate.x + (self.velocity.vx + bx * 4.0) * self.dt,
                y=self._estimate.y + (self.velocity.vy + by * 4.0) * self.dt,
                z=self.position.z + self.rng.gauss(0.0, 0.4),
            )

    def _advance_mission(self) -> None:
        if self.mode is FlightMode.TAKEOFF and self.position.z >= self.mission.altitude - 0.5:
            self.phase = MissionPhase.ENROUTE
            self.mode = FlightMode.MISSION
            self.waypoint_index = 1
            self._pending_mission_events.append(
                MissionEvent(
                    event_type="takeoff_complete",
                    message=f"Takeoff complete at {self.position.z:.0f} m",
                    progress=self._progress(),
                )
            )
        elif self.mode is FlightMode.MISSION and self.phase is MissionPhase.ENROUTE:
            if self.waypoint_index < len(self.waypoints):
                wp = self.waypoints[self.waypoint_index]
                if math.hypot(wp.x - self._estimate.x, wp.y - self._estimate.y) < 3.0:
                    self._pending_mission_events.append(
                        MissionEvent(
                            event_type="waypoint_reached",
                            message=f"Waypoint {self.waypoint_index} reached",
                            progress=self._progress(),
                        )
                    )
                    self.waypoint_index += 1
                    if self.waypoint_index >= len(self.waypoints):
                        self.phase = MissionPhase.LANDING
                        self.mode = FlightMode.LAND
                        self._pending_mission_events.append(
                            MissionEvent(
                                event_type="mission_waypoints_complete",
                                message="All waypoints reached, landing",
                                progress=self._progress(),
                            )
                        )
        elif self.mode is FlightMode.RTL:
            if math.hypot(self.position.x, self.position.y) < 3.0:
                self.phase = MissionPhase.LANDING
                self.mode = FlightMode.LAND
        if self.mode is FlightMode.LAND and self.position.z <= 0.05 and self.t > 1.0:
            self.mode = FlightMode.LANDED
            self.armed = False
            self.finished = True
            reached_all = self.waypoint_index >= len(self.waypoints)
            self.phase = MissionPhase.COMPLETE if reached_all else MissionPhase.ABORTED
            self._pending_mission_events.append(
                MissionEvent(
                    event_type="landed",
                    message="Landed"
                    + (
                        ""
                        if reached_all
                        else f" ({self._land_reason or self._rtl_reason or 'mission aborted'})"
                    ),
                    progress=self._progress(),
                )
            )

    def _progress(self) -> float:
        legs = max(len(self.waypoints) - 1, 1)
        if self.phase is MissionPhase.COMPLETE:
            return 1.0
        if self.phase in (MissionPhase.PENDING, MissionPhase.TAKEOFF):
            return min(0.05, self.position.z / max(self.mission.altitude, 1.0) * 0.05)
        completed = min(self.waypoint_index - 1, legs)
        partial = 0.0
        if self.waypoint_index < len(self.waypoints) and self.phase is not MissionPhase.LANDING:
            prev = self.waypoints[self.waypoint_index - 1]
            wp = self.waypoints[self.waypoint_index]
            leg_len = math.hypot(wp.x - prev.x, wp.y - prev.y) or 1.0
            remaining = math.hypot(wp.x - self._estimate.x, wp.y - self._estimate.y)
            partial = max(0.0, min(1.0, 1.0 - remaining / leg_len))
        waypoint_share = 0.9
        landing_share = 0.1
        progress = waypoint_share * (completed + partial) / legs
        if self.phase is MissionPhase.LANDING and self.waypoint_index >= len(self.waypoints):
            descent = 1.0 - min(1.0, self.position.z / max(self.mission.altitude, 1.0))
            progress = waypoint_share + landing_share * descent
        return max(0.0, min(0.999, progress))

    # ------------------------------------------------------------------ step

    def step(self) -> Observation:
        self.t = round(self.t + self.dt, 6)
        self._advance_transients()
        derived = self._derive()
        self._decide_mode(derived)
        if not self.finished or self.phase is MissionPhase.ABORTED:
            self._move(derived)
        self._update_estimate(derived)
        self._advance_mission()

        changes: list[ComponentStateChange] = []
        for subsystem, state in derived.states.items():
            before = self.previous_states.get(subsystem, ComponentState.UNKNOWN)
            if before != state:
                changes.append(
                    ComponentStateChange(
                        subsystem=subsystem,
                        state_before=before,
                        state_after=state,
                        reason=derived.reasons.get(subsystem, ""),
                        caused_by=derived.causes.get(subsystem) or None,
                    )
                )
        # RECOVERED is a transient label: after it has been observed once it normalizes.
        for subsystem in list(self.recovered_marks):
            if self.previous_states.get(subsystem) is RECOVERED:
                self.recovered_marks.discard(subsystem)
        self.previous_states = dict(derived.states)

        sample = self._sample(derived)
        responses = tuple(self._pending_responses)
        mission_events = tuple(self._pending_mission_events)
        self._pending_responses = []
        self._pending_mission_events = []
        return Observation(
            sample=sample,
            state_changes=tuple(changes),
            responses=responses,
            mission_events=mission_events,
            finished=self.finished,
        )

    def _sample(self, d: _Derived) -> TelemetrySample:
        geo = None
        origin = self.planned_path.origin
        if origin is not None:
            lat = origin.latitude + math.degrees(self.position.y / EARTH_RADIUS)
            lon = origin.longitude + math.degrees(
                self.position.x / (EARTH_RADIUS * math.cos(math.radians(origin.latitude)))
            )
            geo = GeoPosition(
                latitude=lat, longitude=lon, altitude_msl=origin.altitude_msl + self.position.z
            )
        error = math.hypot(self._estimate.x - self.position.x, self._estimate.y - self.position.y)
        target = self._target()
        dist = None
        if target is not None and self.mode is FlightMode.MISSION:
            dist = math.hypot(target.x - self.position.x, target.y - self.position.y)
        return TelemetrySample(
            t=self.t,
            wall_time=utcnow(),
            source=self.source,
            position=Position(
                x=round(self.position.x, 3),
                y=round(self.position.y, 3),
                z=round(self.position.z, 3),
            ),
            geo=geo,
            attitude=Attitude(
                roll=round(self.attitude.roll, 4),
                pitch=round(self.attitude.pitch, 4),
                yaw=round(self.attitude.yaw, 4),
            ),
            velocity=Velocity(
                vx=round(self.velocity.vx, 3),
                vy=round(self.velocity.vy, 3),
                vz=round(self.velocity.vz, 3),
            ),
            mission=MissionStatus(
                phase=self.phase,
                progress=round(self._progress(), 4),
                waypoint_index=min(self.waypoint_index, len(self.waypoints)),
                waypoints_total=len(self.waypoints),
                distance_to_waypoint=None if dist is None else round(dist, 1),
            ),
            flight=FlightStatus(
                mode=self.mode,
                armed=self.armed,
                control_authority=not d.control_lost,
                autonomy=self._autonomy,
            ),
            navigation=NavigationStatus(
                source="gnss" if d.gnss_aiding else "dead_reckoning",
                gnss_fix=d.gnss_aiding,
                position_error=round(error, 2),
                satellites=12 if d.gnss_aiding else 0,
            ),
            communications=CommunicationsStatus(
                c2_link=d.c2_link,
                telemetry_link=d.telemetry_link,
                latency_ms=round(45.0 + d.latency_ms, 1) if d.c2_link else None,
                packet_loss=round(d.packet_loss, 3) if d.c2_link else None,
            ),
            power=PowerStatus(
                voltage=round(self._voltage, 2), remaining=round(self._battery, 4), current=None
            ),
            health=dict(d.states),
        )

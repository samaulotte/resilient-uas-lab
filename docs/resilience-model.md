# Resilience model

This document defines the vocabulary the platform uses to describe what happens to an
autonomous system under degradation. Scenario authors use it to write expectations and
assertions, adapters use it to report what they observe, and the analysis uses it to
compute metrics. Every term below corresponds to a definition in
`packages/core/reslab_core/states.py`, `topology.py`, `engine/scenario_engine.py` or
`analysis/metrics.py`; nothing else in the code base introduces new state strings.

The central idea is that resilience is measured, not assumed. A scenario requests
disturbances and declares expectations; the platform records what the target actually
did and derives every figure from those observations.

## Components and domains

The system under test is described by a topology: components, the domain each belongs
to, dependencies along which a fault may propagate, and trust boundaries a fault must
not cross. The default topology `multirotor-companion-v1` (a generic multirotor with a
companion computer) has 17 components in 7 domains:

| Domain | Components |
| ------ | ---------- |
| `external` | `external.gcs` |
| `communications` | `communications.c2`, `communications.telemetry` |
| `mission_compute` | `mission.compute`, `mission.planner`, `mission.services`, `network.companion_link` |
| `navigation` | `navigation.gnss`, `navigation.estimator`, `sensors.barometer`, `sensors.magnetometer` |
| `flight_control` | `sensors.imu`, `flight_control.core`, `security.gateway` |
| `actuation` | `actuation.motors` |
| `power` | `power.battery`, `power.bus` |

`flight_control` and `actuation` are the critical domains: their impairment constitutes
loss of the flight-critical function. Three components are marked critical:
`sensors.imu`, `flight_control.core` and `actuation.motors`. Loss of any of them means
loss of the flight-critical function. The dependency graph and the trust boundaries
are drawn in [trust boundaries](trust-boundaries.md).

## Component states

A component is always in exactly one of eight states.

| State | Meaning | Healthy | Down |
| ----- | ------- | ------- | ---- |
| `NOMINAL` | Performing within specification, no active fault. Vocabulary for sensors, navigation, communications and power | yes | no |
| `OPERATIONAL` | Performing its function. Vocabulary for flight control, actuation, compute and the command gateway. Equivalent to `NOMINAL` in every calculation | yes | no |
| `DEGRADED` | Still performing its function with reduced quality, capacity or confidence (for example navigation without GNSS aiding) | no | no |
| `UNAVAILABLE` | The function is not being provided (link lost, sensor silent) but the component itself did not fail | no | yes |
| `FAILED` | The component itself failed (crash, fault latch, loss of control) | no | yes |
| `RECOVERING` | A recovery action is in progress (process restart, re-acquisition) | no | yes |
| `RECOVERED` | Back to a healthy state after a fault. Behaves as healthy in every availability calculation; kept distinct so that timelines show the recovery | yes | no |
| `UNKNOWN` | No observation is available for this component | no | no |

Three derived sets matter for the metrics:

- **healthy**: `NOMINAL`, `OPERATIONAL`, `RECOVERED`;
- **impaired**: `DEGRADED`;
- **down**: `UNAVAILABLE`, `FAILED`, `RECOVERING`.

`UNKNOWN` is neither healthy nor unhealthy. Components an adapter cannot observe stay
`UNKNOWN` and are excluded from domain availability so that partial observability does
not zero out a domain the adapter cannot see. Weighted navigation integrity treats
`UNKNOWN` as full integrity for the same reason.

## System mode

The aggregated operating mode of the whole system at an instant is derived from the
component states and the set of critical components (`aggregate_system_mode`):

| Mode | Condition |
| ---- | --------- |
| `NOMINAL` | Every observed component is healthy |
| `DEGRADED` | At least one component is degraded or down, but no critical component is down and no component has failed |
| `FAILED` | Any component is `FAILED`, or a critical component is down |

The time spent in each mode is reported as `time.nominal`, `time.degraded` and
`time.failed`. The distinction between a degraded system and a failed one is the
subject of [degraded modes](degraded-modes.md) and [safety model](safety-model.md).

## Flight modes and mission phases

Adapters report a vehicle-level `FlightMode` (`IDLE`, `TAKEOFF`, `MISSION`, `HOLD`,
`RTL`, `LAND`, `LANDED`, `UNKNOWN`) and a `MissionPhase` (`PENDING`, `TAKEOFF`,
`ENROUTE`, `HOLDING`, `RETURNING`, `LANDING`, `COMPLETE`, `ABORTED`). `HOLD`, `RTL`,
`LAND` and `LANDED` are the safe-state modes. Time in `HOLD` or `RTL` (or in the
`HOLDING` phase) is time in which the mission is not progressing and reduces mission
continuity. A mission is complete when the last sample reports phase `COMPLETE`.

`FlightStatus.control_authority` states whether the flight core has full control of the
vehicle, and `FlightStatus.autonomy` names who is driving it: `mission` (the mission
planner), `local` (onboard autonomy without ground supervision) or `failsafe`.

## Effects

An effect is an abstract consequence a subsystem experiences. The fault catalog
defines eleven: `unavailable`, `intermittent`, `degraded`, `erroneous`, `stuck`,
`restart`, `crash`, `latency`, `packet_loss`, `resource_pressure`,
`temporary_disconnect`. `restart` and `crash` are transient (the target recovers on its
own); the rest are persistent until cleared, optionally bounded by a duration.
`temporary_disconnect` requires a duration. Effects never describe how a disturbance
is produced, only what the target experiences. The full table, with the subsystems
each effect applies to and its parameters, is in [scenario format](scenario-format.md).

## Events

Every discrete thing that happens during a run is a `RunEvent` with a monotonic
sequence number, a simulation time, a source (`scenario`, `adapter`, `engine`,
`analysis`, `platform`), a kind, a machine-readable `event_type`, a severity, and
optionally the subsystem, the states before and after and the scenario event that
caused it. The kind is a scientific classification; the distinction matters because a
requested disturbance is not evidence that the system was disturbed, and an expected
response is not evidence that it happened.

| Kind | Meaning |
| ---- | ------- |
| `INJECTION_REQUEST` | The scenario engine asked the adapter to inject an effect |
| `INJECTION_APPLIED` | The adapter confirmed the effect is active in the target |
| `INJECTION_REJECTED` | The adapter could not apply the effect (or the adapter does not support it at all) |
| `INJECTION_CLEARED` | The effect was removed (duration elapsed or scenario end) |
| `OBSERVED_EFFECT` | A component state change into a non-healthy state observed in the target |
| `SYSTEM_RESPONSE` | An autonomous reaction of the target (mode change, failsafe, autonomy hand-over) |
| `RECOVERY` | A component returned to a healthy state |
| `EXPECTATION_RESULT` | An expectation declared in the scenario was decided |
| `ASSERTION_RESULT` | A scenario assertion was evaluated during analysis |
| `MISSION` | Mission progress (started, takeoff, waypoint reached, complete, timeout) |
| `LIFECYCLE` | Run lifecycle transition, cancellation or target failure |
| `LOG` | Informational message (for example a state change between two healthy labels) |

Severities are `info`, `low`, `medium`, `high`, `critical`. The engine assigns them to
observed state changes as follows: `DEGRADED` is `medium`, `UNAVAILABLE` is `high`,
`FAILED` is `critical`, `RECOVERING` is `high` when entered from a healthy state and
`info` when it follows another unhealthy state; any critical component going down is
`critical` regardless of the state. Rejected injections are `high`; failed
expectations are `high`; a mission timeout is `high`; loss of a target is `critical`.

Metadata on `OBSERVED_EFFECT` and `RECOVERY` events records `direct` (whether the
change is on the injected subsystem itself or a propagated consequence) and the
adapter's `reason`.

## Cause attribution

When the adapter does not state which scenario event caused a change, the engine
attributes it: first to an active injection on the same subsystem, then to an active
injection on one of the subsystem's upstream providers in the topology, otherwise the
change is unattributed. Attribution is best effort and is recorded in
`scenario_event_id`; the analysis treats unattributed changes as independent or
propagated faults.

## Disturbance window and recovery

Two intervals describe a fault on a subsystem:

- the **fault duration**, from the first observed non-healthy state to the return to a
  healthy state;
- the **disturbance window**, the time during which the causing injection (or a bounded
  injection on the subsystem or one of its upstream providers) was active.

**Recovery time** is measured from the end of the disturbance window to the return to a
healthy state. When the injection is bounded, the window ends at the `INJECTION_CLEARED`
event with reason `duration elapsed`; when several bounded injections act on the
subsystem or its providers, the latest clear within the fault counts. When nothing
bounded the disturbance (transient effects such as `restart` and `crash`, or a fault
the target inflicted on itself), recovery time is measured from the fault start. This
is why a 40 s GNSS outage followed by re-acquisition 0.1 s after fixes return yields a
fault duration of 40 s and a recovery time of 0.1 s: the system cannot be blamed for
the length of the disturbance, only for how quickly it recovers once the disturbance
ends.

A fault that was still open at the end of the run **required recovery** unless its
causing injection persisted until scenario end (it was cleared with reason `scenario
end` or never cleared) and was not transient. A subsystem that stays `UNAVAILABLE`
because the scenario never restored it is not a failed recovery.

Mean time to recovery (`recovery.mttr`), the maximum, the success rate and per
subsystem maxima follow from these records. See [metrics](metrics.md).

## Expectations versus assertions

An **expectation** is attached to an event: after this injection, this subsystem should
be in this state within this window. It is decided by the engine during the run from
observed states (rules in [scenario format](scenario-format.md)) and produces an
`EXPECTATION_RESULT` event. Expectations describe the immediate, local response.

An **assertion** is a statement about the whole run, evaluated during analysis against
the metrics: `recovery.mission_compute < 10s`, `mission.completion >= 0.80`. Assertions
with severity `critical` are hard gates. Assertions describe the outcome.

Both must describe observable behavior in this vocabulary. An expectation cannot ask
the target to do something; it can only state what will be verified.

## Containment and propagation

The **injected components** are those for which an injection was applied. The
**affected components** are those observed in a non-healthy state. **Propagated
components** are affected components that were not injected. The topology gives a
**propagation depth** for each affected component: the shortest dependency distance
from an injected component, following only edges whose both ends are affected (a
healthy component stops propagation). Injected components have depth 0; affected
components unreachable that way have depth -1 and are treated as independent faults.

A fault is **contained** when no affected component belongs to a critical domain
(`flight_control` or `actuation`). A **trust boundary is crossed** when a dependency
marked `crosses_trust_boundary` has both ends affected; in the default topology that is
the edge from `network.companion_link` to `security.gateway`. The mission/flight
boundary and its enforcement point are described in
[trust boundaries](trust-boundaries.md).

## Safety

Safety in this model is the preservation of control: the flight core keeps control
authority and never leaves a healthy state. **Loss of control** is any sample with
`control_authority` false or `flight_control.core` in `FAILED`. **Flight control
available** means the flight core spent no time in a non-healthy state and no
`OBSERVED_EFFECT` ever reported it unhealthy. **Safety preserved** requires both. A
**safe state** was reached when the target emitted a `SYSTEM_RESPONSE` with
`safe_state=true` (hold, return to launch, land). The [safety model](safety-model.md)
develops these definitions.

## Benchmark result

Once analyzed, a run has a result: `passed`, `failed` or `inconclusive`. `passed` and
`failed` are only emitted for runs that completed their scenario; `inconclusive` marks
runs that could not be fully executed or analyzed (cancelled, failed, or the target
went away). The result is decided by hard gates, and the numeric resilience score is
informative on top of it; see [scoring](scoring.md).

## Reading a run

A useful order when reading a run in Mission Control or in `report.html`:

1. `INJECTION_APPLIED` versus `INJECTION_REJECTED`: did the disturbance happen at all?
2. `OBSERVED_EFFECT` on the injected subsystem: did the target notice?
3. `OBSERVED_EFFECT` on other subsystems and the blast radius: how far did it spread,
   and did it stay out of the flight-critical domain?
4. `SYSTEM_RESPONSE`: what did the autonomy do about it, and was it a safe state?
5. `RECOVERY` and the recovery records: how long after the disturbance ended did each
   subsystem come back?
6. `EXPECTATION_RESULT` and the assertions: did the outcome match what the scenario
   author declared?

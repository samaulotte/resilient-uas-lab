# Safety model

"Safety" in Resilient UAS Lab has a precise, narrow meaning: the flight-critical
function is preserved while other parts of the system degrade. This document defines
that meaning, explains how the platform observes it, how it reports it and how it
weighs it, and states clearly what the platform does not and cannot say about the
safety of any real aircraft.

Everything here is derived from `packages/core/reslab_core/states.py`, `topology.py`,
`engine/scenario_engine.py`, `analysis/metrics.py` and `analysis/scoring.py`.

## The flight-critical function

The topology marks three components as critical: `sensors.imu` (primary attitude
sensing), `flight_control.core` (the flight controller running attitude and position
control loops) and `actuation.motors`. Loss of any of them means loss of the
flight-critical function. Two domains, `flight_control` and `actuation`, are the
critical domains; `sensors.imu` and `security.gateway` belong to `flight_control`
alongside the core.

The design intent recorded in the topology is that the flight core keeps full control
authority if everything upstream of the mission/flight boundary fails. A resilient
system, in this model, is one where a mission computer can crash, a datalink can
vanish and a GNSS receiver can go silent while the flight core keeps flying, enters a
safe state when the declared policy says so, and never loses control.

## Observing safety

The platform never assumes a safe outcome. Safety is observed through three channels.

### Control authority

Every telemetry sample carries `flight.control_authority`, true while the flight core
has full control of the vehicle. The mock adapter sets it false when the flight core is
`RECOVERING` or `FAILED` or when the motors are down, and then aborts the mission with a
`loss_of_control` system response. The PX4 adapter sets it false when the link is down
or the flight mode is unknown.

### Component states

The flight core is observed like any other component. `OBSERVED_EFFECT` events on
`flight_control.core` (or on any critical component going down) are emitted with
severity `critical`. Time spent by the flight core outside the healthy states, and any
`OBSERVED_EFFECT` reporting it non-healthy, both count against
`flight_control.available`.

### System responses

Autonomous reactions of the target are `SYSTEM_RESPONSE` events. Those that place the
vehicle in a safe state carry `safe_state: true`: in the mock, `failsafe_hold`,
`failsafe_rtl` and `failsafe_land`; in the PX4 adapter, a mode change from `MISSION`
to `HOLD`, `RTL` or `LAND`, and STATUSTEXT messages mentioning a failsafe. Responses
that are not safe states (`local_autonomy_active`, `mission_resumed`,
`c2_authority_restored`, `loss_of_control`) are still recorded, with `safe_state:
false`.

## Safety metrics

| Metric | Definition | Where it appears |
| ------ | ---------- | ---------------- |
| `safety.loss_of_control` | Any sample with `control_authority` false, or the flight core `FAILED` in any sample | Hard gate `control_authority`; summary `loss_of_control`; safety dimension |
| `flight_control.available` | The flight core spent no time in a non-healthy state and no `OBSERVED_EFFECT` reported it non-healthy | Critical assertion in every starter scenario |
| `control.availability` | Fraction of the run during which the flight core was healthy (excluding `UNKNOWN`) | Safety dimension score |
| `safety.preserved` | `not loss_of_control and flight_control_available` | Summary `safety_preservation: PASS/FAIL` |
| `safety.safe_state_reached` | Any safe-state system response | Recovery metrics `safe_state_entered` |
| `recovery.time_to_safe_state` | From the most recent observed fault at or before the first safe-state response to that response | Recovery metrics, comparison view |
| `time.failed` | Time the aggregated system mode was `FAILED` (any component failed, or a critical component down) | Mode metrics; default regression threshold `max: 0.0` |
| `containment.critical_domain_reached` | Any affected component in `flight_control` or `actuation` | Containment dimension zeroed; critical assertion `containment.flight_domain_affected == false` |

`flight_control.available` is intentionally stricter than `control.availability`. A
flight core that was degraded for one sample out of a thousand has availability 0.999
but is not "available" in the sense of the critical assertion. This asymmetry is what
lets a scenario say, at severity `critical`, that the flight core must never leave its
operational state.

## How safety decides the result

Three mechanisms, in decreasing order of force:

1. **Hard gate `control_authority`.** Loss of control makes the run `failed` regardless
   of the score (`loss of control observed`).
2. **Critical assertions.** All seven starter scenarios declare
   `flight_control.available == true`, `safety.loss_of_control == false` and
   `containment.flight_domain_affected == false` at severity `critical`. Any failure is
   a hard gate failure. A scenario without a critical assertion gets a loader warning
   because it can then never hard-fail.
3. **The safety dimension.** Thirty of one hundred points in the default profile: zero
   on loss of control, otherwise `control.availability`. The containment dimension
   (fifteen points) is zeroed when a fault reaches a critical domain.

Safety therefore dominates the result twice: once as a gate, once as the largest
dimension.

## The recovery policy: expectations, not commands

A scenario declares a `recovery` policy (`gnss_loss`, `datalink_loss`, `compute_loss`,
`hold_timeout`, `max_dead_reckoning`). The model file is explicit that these are
expectations the platform verifies, not commands it executes. The platform never sends
a mode change to a target. The adapter passes the policy to the target (the mock
adapter implements it in its behavioral model; the PX4 adapter uploads a mission with
return-to-launch after completion and otherwise lets PX4's own failsafes act) and the
platform records what actually happened.

For example, with `compute_loss: hold` and `hold_timeout: 30s`, the mock enters `HOLD`
when the mission command path is lost, escalates to `LAND` if the hold lasts longer
than 30 s, and resumes the mission when the path comes back. Each of these is a
`SYSTEM_RESPONSE` in the record. The observable behaviors of every policy value are
described in [degraded modes](degraded-modes.md).

## Severity escalation

The engine escalates severities so that the event feed and the report make the
safety-relevant events stand out:

- an observed `FAILED` state is `critical`;
- any down state (`UNAVAILABLE`, `FAILED`, `RECOVERING`) on a critical component is
  `critical`;
- `UNAVAILABLE` elsewhere is `high`, `DEGRADED` is `medium`;
- a `RECOVERING` state entered from a healthy state is `high`, entered from another
  unhealthy state (a crash followed by a restart) is `info`;
- a safe-state response is `medium`, other responses `info`;
- a rejected injection is `high`; an unsupported injection or a target failure is
  `critical`.

The report summary counts `critical_failures` as observed effects of severity
`critical`, and Mission Control raises active alerts (for example `GNSS LOST`) from the
latest sample.

## Injecting into the flight-critical domain

The fault catalog allows a limited set of effects on the critical components
(`sensors.imu`: `degraded`, `erroneous`, `intermittent`; `flight_control.core`:
`degraded`, `restart`, `resource_pressure`; `actuation.motors`: `degraded`,
`intermittent`). Doing so is legitimate: it is how one tests what happens when the
protected domain itself is hit. The loader warns (`flight_critical_target`) so that
the intent is explicit, and such a scenario should expect `containment` to be zero and
`flight_control.available` to be false; its critical assertions must be written
accordingly, otherwise it will always fail.

In the mock, a degraded IMU degrades the flight core and adds attitude noise; a flight
core `restart` makes control authority false and aborts the mission with loss of
control; degraded motors reduce speed and add noise, and motors down mean loss of
control.

## What the safety model does not claim

- It does not certify an aircraft, a flight stack or an autopilot configuration. It
  measures the behavior of a target as observed through an adapter, in a scenario the
  author designed.
- It has no notion of airspace, people on the ground, geofences, weather, energy
  reserves beyond a battery ratio, or regulations. A `passed` result means the declared
  expectations and assertions held for this run.
- It observes only what the adapter reports. The mock adapter reports every component;
  the PX4 adapter derives a subset from MAVLink telemetry and reports the rest as
  `UNKNOWN`. A flight core that is never observed is never counted as unavailable.
- It operates on simulations and recordings only. No adapter in this repository
  connects to hardware, and hardware adapters are out of scope.
- Its safe-state notion is the vehicle-level mode reported by the target (hold, return,
  land), not an assessment of whether that mode was the right choice.

The model is useful precisely because it is narrow: it lets an engineer say, with
evidence, "in this scenario the flight core never lost authority and the fault never
reached the flight-critical domain", and lets a regression check flag the day that
stops being true.

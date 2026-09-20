# Degraded modes

A resilient system rarely goes from fully working to failed in one step. It passes
through degraded modes in which it keeps delivering its function with reduced quality,
hands authority to a local fallback, or parks itself in a safe state until conditions
improve. This document describes how the platform represents degraded modes, how the
mock adapter realizes them (so that authors know what a starter scenario will exhibit),
what the declared recovery policy means, and how time spent in degraded modes is
measured.

## Two levels of degradation

**Component level.** A component in `DEGRADED` still performs its function with reduced
quality, capacity or confidence. It is impaired, not down. Examples from the mock's
behavioral model: the navigation estimator in dead reckoning, a planner running at a
reduced rate under resource pressure, a datalink with added latency or packet loss.

**System level.** The aggregated system mode is `DEGRADED` when at least one component
is degraded or down but no critical component is down and nothing has failed
(`aggregate_system_mode`). The system is still flying under control; something in it
is not working properly. It becomes `FAILED` the moment any component is `FAILED` or a
critical component is down. `time.degraded` and `time.failed` measure how long the
system spent in each.

A mission computer that is `RECOVERING` after a restart is down at component level but
the system is only `DEGRADED`, because the mission computer is not critical. That is the
outcome the starter scenarios test for: a compute restart must be a degraded mode of the
system, never a failed one.

## The recovery policy

The scenario's `recovery` block declares how the target is expected to react. These
are expectations the platform verifies, never commands it executes; the adapter maps
them to the target and the platform records what happened.

| Field | Values | Default |
| ----- | ------ | ------- |
| `gnss_loss` | `dead_reckoning`, `hold`, `land` | `dead_reckoning` |
| `datalink_loss` | `continue`, `hold`, `rtl` | `continue` |
| `compute_loss` | `hold`, `land`, `rtl` | `hold` |
| `hold_timeout` | duration | `60s` |
| `max_dead_reckoning` | duration | `90s` |

The mock adapter (`adapters/mock/reslab_adapter_mock/simulation.py`) implements the
policy with the priority `LAND > RTL > HOLD > MISSION`: when several conditions ask for
different modes at the same instant, landing wins over returning, which wins over
holding. Takeoff continues under a hold request so the vehicle reaches a safe altitude
first.

## Degraded modes in the mock adapter

The mock is a deterministic component-state model, not a physics simulator. Its
behaviors are simple on purpose so that every number in a report can be reasoned about.
The following modes are the ones the starter scenarios exercise.

### Navigation without GNSS aiding (dead reckoning)

GNSS aiding is lost when the receiver is `UNAVAILABLE`, `FAILED` or `RECOVERING`, or
when an `erroneous` or `stuck` output has been active for more than one second (the
estimator's consistency checks reject it). The estimator then goes `DEGRADED` with
reason `dead reckoning: GNSS aiding lost`, the position estimate integrates velocity
with a seeded, slowly wandering bias, the vehicle steers toward its drifting estimate
of the waypoint (so the true path deviates by the estimation error), cruise speed is
capped at 85 percent, and telemetry reports `navigation.source: dead_reckoning`,
`gnss_fix: false`, zero satellites and a growing `position_error`.

What happens next depends on `gnss_loss`:

- `dead_reckoning`: the mission continues until the unaided time exceeds
  `max_dead_reckoning`, then the vehicle holds (`navigation without GNSS aiding`);
- `hold`: the vehicle holds immediately;
- `land`: the vehicle lands (`GNSS aiding lost`).

A `degraded` GNSS receiver keeps aiding the estimator, which is `DEGRADED` with reason
`degraded GNSS aiding`. Faulty barometer or magnetometer outputs also degrade the
estimator (`barometer rejected by estimator`, `magnetometer rejected by estimator`)
without affecting aiding. When fixes return the estimator recovers on the next sample.

### Mission without ground supervision (local autonomy)

The C2 link is down when `communications.c2` is down or the ground station is
unhealthy; a ground station outage shows as a degraded C2 link (`ground station
unavailable`). Telemetry reports `c2_link: false` and no latency or packet-loss figures.
Autonomy attribution changes from `mission` to `local` and the target emits the
response `local_autonomy_active` ("Local autonomy active: mission continues without C2
link"); when the link returns, `c2_authority_restored`.

The `datalink_loss` policy decides the mode: `continue` keeps flying the mission,
`hold` holds (`C2 link lost`), `rtl` returns to launch. Latency and packet loss on the
link degrade the component (`added latency`, `packet loss`) and appear in telemetry
(`latency_ms` is 45 ms plus the injected value; `packet_loss` is the injected ratio)
without breaking the link. Onboard compute is not affected by ground link loss, which
`datalink-loss` asserts with `compute.availability == 1.0`.

### Loss of the mission command path

Commands reach the flight core through planner, companion link and command gateway.
The path is lost when the planner is down (`mission planner unavailable`), the
companion link is down (`companion link down`) or the command gateway is down
(`command gateway unavailable (fail-closed)`). The `compute_loss` policy then applies:
`hold` (the default), `rtl` or `land`. A degraded link or gateway only slows the
vehicle to 85 percent.

A mission computer that is down (`restart`, `crash`, `unavailable`) takes its hosted
processes with it: planner and services become `UNAVAILABLE` with reason `host down`.
A `restart` puts the computer in `RECOVERING` for `restart_time` (a parameter, or a
seeded value between 3.6 s and 5.2 s), a `crash` in `FAILED` for `watchdog_time`
(parameter, or 1.5 s to 2.5 s) and then `RECOVERING` for a restart period. When the
host is back it is reported `RECOVERED` for one sample, its processes return to
`OPERATIONAL` or `NOMINAL`, and if the vehicle was holding it resumes with the response
`mission_resumed`.

### Resource pressure

`resource_pressure` on the mission computer (or a `degraded` computer) degrades the
planner with reason `reduced planning rate` and scales cruise speed by
`1 - 0.6 * load`, with a floor of 35 percent. A planner degraded on its own caps speed
at 70 percent. Nothing here forces a hold, which `resource-pressure` checks with
`mission.continuity >= 0.95`.

### Hold escalation

Whenever a hold is requested, the mock records when it began. If the hold lasts longer
than `hold_timeout` the vehicle lands with reason `hold timeout (<original reason>)`.
This is the only path from a degraded mode to a terminal safe state that does not go
through a policy value of `land`.

### Power

A degraded battery scales endurance and, below a `level` of 0.4 (or below 15 percent
remaining charge), triggers a return to launch (`low battery`). A power bus that is
`UNAVAILABLE` or degraded below `level` 0.5 causes a companion brownout: the mission
computer goes `RECOVERING` (`brownout restart`) for 3 s to 4.5 s and then recovers.
Speed is scaled by `0.6 + 0.4 * battery_factor`.

### Flight-critical degradation

An unhealthy IMU degrades the flight core (`attitude estimate degraded`) and adds
attitude noise. A degraded flight core slows the vehicle to 80 percent and adds noise;
a flight core that is `RECOVERING` or `FAILED` is loss of control, the mission is
aborted and the run ends. Degraded motors slow the vehicle to 75 percent; motors down
are loss of control. These are the modes in which the system is `FAILED` rather than
`DEGRADED`.

## System responses emitted by the mock

| `response_type` | Trigger | Safe state |
| --------------- | ------- | ---------- |
| `failsafe_hold` | Mode changed to `HOLD` | yes |
| `failsafe_rtl` | Mode changed to `RTL` | yes |
| `failsafe_land` | Mode changed to `LAND` for a failsafe reason | yes |
| `mission_resumed` | Mode changed from `HOLD` back to `MISSION` | no |
| `local_autonomy_active` | C2 link lost while the mission continues | no |
| `c2_authority_restored` | C2 link back after local autonomy | no |
| `loss_of_control` | Flight core or motors lost control authority | no |

Each becomes a `SYSTEM_RESPONSE` event with `safe_state` in its metadata; the first
safe-state response sets `recovery.time_to_safe_state`.

## Measuring time in degraded modes

| Metric | What it measures |
| ------ | ---------------- |
| `time.nominal`, `time.degraded`, `time.failed` | Time-weighted system mode over the run |
| `mission.continuity` | `1 - time in HOLD or RTL (or phase HOLDING) / total`: how much of the run the mission was actually progressing |
| `time_in_mission_modes` | Time in `MISSION`, `TAKEOFF` or `LAND` |
| `navigation.integrity` | Weighted estimator availability: degraded time counts half |
| `component_time_in_state` | Seconds per state for every component |
| `subsystem_timeline` | The same information as intervals, drawn in Mission Control and `report.html` |

`compound-degradation` on the mock spends roughly the first 30 s nominal and the rest
of its 145 s degraded (GNSS and C2 are never restored in that scenario) with zero
seconds failed; its mission continuity is about 0.97 because the 4.9 s compute restart
put the vehicle in hold. Those are the shapes the metrics are designed to show: long
degraded operation is acceptable, a failed mode is not, and holds cost continuity.

## Writing scenarios around degraded modes

- Use expectations to check the immediate degraded state:
  `navigation.estimator DEGRADED within 3s` after a GNSS injection,
  `mission.planner DEGRADED within 2s` after resource pressure,
  `flight_control.core OPERATIONAL within 1s` to assert the core is untouched.
- Use `RECOVERED` expectations for transient effects
  (`mission.compute RECOVERED within 10s`).
- Bound injections with `duration` when you want to measure recovery; leave them
  unbounded when you want to measure sustained degraded operation (the recovery
  metrics then exclude them from the required set).
- Set the recovery policy to what you expect the target to do and assert the
  consequence: `mission.continuity >= 0.95` when a hold must not happen,
  `safety.safe_state_reached == true` when it must.
- Assert `time.failed` through the regression thresholds (`max: 0.0`) rather than in
  every scenario; the critical assertions on control authority and containment already
  cover the failed mode.

Other adapters realize degraded modes differently. The PX4 adapter derives them from
PX4 telemetry (GPS fix type and satellite count, estimator health flags, flight mode)
and cannot observe several components at all; see [PX4 integration](px4-integration.md).

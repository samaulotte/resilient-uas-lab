# Metrics

Every metric is computed from observed data (run events and telemetry samples), never
from what the scenario requested. The implementation is `compute_metrics` in
`packages/core/reslab_core/analysis/metrics.py`; this document mirrors it. Metrics
appear in `report.json` under `metrics`, in the run detail Metrics tab, at
`GET /api/v1/runs/{id}/metrics`, and, flattened, in the assertion context that scenario
assertions are evaluated against.

Conventions: durations are seconds of simulation time; ratios are in `[0, 1]`
(assertions may write them as percentages, `80%` is `0.8`); `None` (JSON `null`) means
the metric could not be measured for this run.

## Inputs and the run interval

The analysis receives the run's events sorted by `(simulation_time, sequence)` and its
telemetry samples sorted by `t`. The run interval `total` is the time between the first
and the last sample. If fewer than two samples exist, `total` falls back to the latest
event time. Time-weighted metrics integrate over consecutive sample pairs: each sample's
state holds until the next sample. Because the mock adapter samples at
`simulation.telemetry_rate_hz` (default 10 Hz) the resolution is 0.1 s.

## Mission

| Metric | Definition |
| ------ | ---------- |
| `mission.completion` | Maximum `mission.progress` reported by any sample (the adapter's completion ratio; the mock counts 90 percent for waypoints and 10 percent for the landing) |
| `mission.completed` | The last sample's mission phase is `COMPLETE` |
| `mission.duration` | `total`, the run interval |
| `time_in_hold` | Time in flight mode `HOLD` or `RTL`, or in mission phase `HOLDING` |
| `time_in_mission_modes` | Time in flight mode `MISSION`, `TAKEOFF` or `LAND` (not otherwise counted as hold) |
| `mission.continuity` | `1 - time_in_hold / total`, clamped to `[0, 1]`; `1.0` when `total` is zero |

## Availability

`availability.<domain>` is the fraction of the run during which every observed
component of the domain was healthy. A component reported as `UNKNOWN` at a sample is
not observed at that sample and is excluded from the check, so an adapter with partial
observability does not zero out a domain it cannot see. The value is `1.0` when there
are no samples.

| Metric | Components |
| ------ | ---------- |
| `control.availability` (also `flight_control.availability`) | `flight_control.core` |
| `navigation.availability` | `navigation.estimator` |
| `communications.availability` | `communications.c2`, `communications.telemetry` |
| `compute.availability` | `mission.compute`, `mission.planner`, `mission.services`, `network.companion_link` |
| `power.availability` | `power.battery`, `power.bus` |

Note that control and navigation availability look at a single component each: the
flight core and the estimator are the components whose function the domain exists to
deliver. A degraded GNSS receiver does not reduce navigation availability by itself; it
reduces it only if the estimator leaves the healthy set.

### Navigation integrity

`navigation.integrity` is a weighted availability of `navigation.estimator`: healthy or
`UNKNOWN` states weigh `1.0`, `DEGRADED` weighs `0.5`, down states weigh `0.0`, all
integrated over time and divided by `total`. A run whose estimator spent 40 s of a
135 s run in dead reckoning therefore reports about `0.85`. This is the metric the
`navigation` score dimension uses.

## Recovery

Recovery metrics are built from `RecoveryRecord` entries, one per fault. A fault opens
on the first `OBSERVED_EFFECT` that puts a subsystem in a non-healthy state (further
non-healthy transitions of the same open fault are ignored) and closes on the next
`RECOVERY` event for that subsystem.

| Record field | Definition |
| ------------ | ---------- |
| `subsystem` | The component |
| `fault_state` | The state that opened the fault |
| `fault_started_at` | Simulation time of the opening `OBSERVED_EFFECT` |
| `recovered_at` | Simulation time of the `RECOVERY` event, or `null` |
| `fault_duration` | `recovered_at - fault_started_at`, or `null` |
| `disturbance_cleared_at` | End of the disturbance window (below), or `null` |
| `recovery_time` | `recovered_at - reference` (below), or `null` |
| `caused_by` | Scenario event id when attributable |
| `direct` | `true` when the fault is on the injected subsystem itself |
| `recovery_expected` | `false` when the injected effect persisted until scenario end |

### The disturbance window

The disturbance ends when the last bounded injection acting on the subsystem is
cleared. Candidates are the `INJECTION_CLEARED` events with reason `duration elapsed`
for the attributed cause, and those for any injection on the subsystem itself or on
its upstream providers in the topology whose clear time lies within
`[fault_started_at, recovered_at]`. The latest candidate is `disturbance_cleared_at`.

The reference from which recovery time is measured is
`max(fault_started_at, min(disturbance_cleared_at, recovered_at))`. With no candidate
(transient effects such as `restart` and `crash`, unbounded injections, faults the
target inflicted on itself) the reference is the fault start and recovery time equals
fault duration.

Two records from real runs of the starter scenarios illustrate this. In `gnss-loss` the
receiver is unavailable for 40 s from T+35.0; the estimator is degraded from T+35.1
and both recover at T+75.1: `fault_duration` 40.0, `disturbance_cleared_at` 75.0,
`recovery_time` 0.1 for both. In `compound-degradation` the mission computer restarts
at T+60 (a transient effect, no clear): `fault_started_at` 60.1, `recovered_at` 65.0,
`fault_duration` 4.9, `recovery_time` 4.9, and the planner and services, which went
`UNAVAILABLE` because their host was down, carry the same times with `direct: false`.

### Faults still open at the end

A subsystem still non-healthy when the run ends gets a record with `null` times. It is
counted as requiring recovery unless the causing injection persisted to scenario end
(its clear reason is `scenario end`, or it was never cleared) and the effect is neither
`restart` nor `crash`. In `compound-degradation` the GNSS receiver and the C2 link are
made unavailable without duration; they and the degraded estimator stay open and are
recorded with `recovery_expected: false`, so the run's recovery success rate is `1.0`
(3 of 3) rather than 3 of 6.

### Aggregates

| Metric | Definition |
| ------ | ---------- |
| `recovery.required` | Number of records with `recovery_expected` |
| `recovery.count` | Number of required records with a `recovery_time` |
| `recovery.success_rate` | `count / required`; `null` when nothing required recovery |
| `recovery.mttr` | Mean `recovery_time` over recovered records; `null` when none recovered |
| `recovery.max` | Maximum `recovery_time`; `null` when none recovered |
| `recovery.<subsystem>` | Maximum `recovery_time` per subsystem, the id with its dot replaced by an underscore (`recovery.mission_compute`, `recovery.navigation_estimator`) |
| `recovery.time_to_safe_state` | Time from the most recent observed fault at or before the first safe-state `SYSTEM_RESPONSE` to that response; `null` when no safe state was entered |
| `safe_state_entered` | Any `SYSTEM_RESPONSE` with `safe_state` true |

Per subsystem keys exist only for subsystems that recovered during the run. An
assertion such as `recovery.navigation_estimator < 5s` is therefore `not_evaluated`
when the estimator never degraded, and `failed` when it degraded and did not recover.

## Propagation (blast radius)

| Metric | Definition |
| ------ | ---------- |
| `injected_components` | Subsystems with an `INJECTION_APPLIED` event |
| `affected_components` | Subsystems with an `OBSERVED_EFFECT` into a non-healthy state |
| `propagated_components` | Affected components that were not injected |
| `containment.propagated_components` | Their number (`propagation_count`) |
| `containment.affected_components` | Number of affected components |
| `depths` | For every affected component, the shortest dependency distance from an injected component following only edges whose both ends are affected; injected components are 0, unreachable ones -1 |
| `containment.propagation_depth` | Maximum non-negative depth (0 when nothing propagated) |
| `affected_domains`, `injected_domains`, `propagated_domains` | The domains of the respective components; `propagated_domains` are affected domains with no injected component |
| `containment.affected_domains` | Number of affected domains |
| `containment.critical_domain_reached` | Any affected domain is `flight_control` or `actuation` |
| `containment.flight_domain_affected` | Same value as `critical_domain_reached` |
| `containment.contained` | `not critical_domain_reached` |
| `containment.boundary_crossed` | A dependency with `crosses_trust_boundary` has both its provider and its dependent affected (in the default topology: `network.companion_link` to `security.gateway`) |

The depth computation (`SystemTopology.propagation_depths`) is a breadth-first search
from the injected components over the `depends_on` edges. In `gnss-loss` the receiver
is depth 0 and the estimator depth 1; the flight core, which depends on the estimator
but stayed healthy, is not affected and stops the search.

`propagated_domains` is what the containment score penalizes: a fault that spreads
within the domain it was injected into is not penalized, one that reaches another
non-critical domain costs a quarter of the dimension per domain, and one that reaches a
critical domain zeroes it (see [scoring](scoring.md)).

## System modes

Each sample's health map is aggregated with `aggregate_system_mode` (see
[resilience model](resilience-model.md)) and the time until the next sample is added to
that mode's counter.

| Metric | Definition |
| ------ | ---------- |
| `time.nominal` | Time in mode `NOMINAL` |
| `time.degraded` | Time in mode `DEGRADED` |
| `time.failed` | Time in mode `FAILED` (any component `FAILED`, or a critical component down) |
| `time.total` | `total` |

A run in which GNSS is unavailable for the rest of the mission spends most of its time
in `DEGRADED`; `compound-degradation` reports about 30 s nominal and 115 s degraded.
`time.failed` is expected to be `0.0` for a resilient system and is one of the default
regression thresholds.

## Safety

| Metric | Definition |
| ------ | ---------- |
| `safety.loss_of_control` | Any sample with `flight.control_authority` false, or `flight_control.core` reported `FAILED` in any sample |
| `flight_control.available` | `flight_control.core` spent no time in a non-healthy state and no `OBSERVED_EFFECT` reported it non-healthy |
| `safety.preserved` | `not loss_of_control and flight_control_available` |
| `safety.safe_state_reached` | Any `SYSTEM_RESPONSE` with `safe_state` true |
| `control_availability` | Same as `control.availability` |

`flight_control.available` is stricter than availability: a single degraded sample of
the flight core makes it `false` even though availability may still be `0.99`. This is
deliberate; it is the assertion the starter scenarios use as a critical gate.

## Event counts

| Metric | Counts |
| ------ | ------ |
| `events.injected` | `INJECTION_REQUEST` |
| `events.applied` | `INJECTION_APPLIED` |
| `events.rejected` | `INJECTION_REJECTED` |
| `cleared` | `INJECTION_CLEARED` |
| `events.observed_effects` | `OBSERVED_EFFECT` |
| `system_responses` | `SYSTEM_RESPONSE` |
| `events.recoveries` | `RECOVERY` |
| `expectations_passed`, `events.expectations_failed` | `EXPECTATION_RESULT` by `passed` |
| `degraded_transitions` | `OBSERVED_EFFECT` into `DEGRADED` |
| `failed_transitions` | `OBSERVED_EFFECT` into `FAILED` or `UNAVAILABLE` |

`events.injected` counts requests, `events.applied` confirmations. The report summary
shows both as `faults_injected` and `faults_applied` so that a scenario whose
injections were rejected cannot look like a passed test.

## Per-component time in state

`component_time_in_state` gives, for every subsystem, the seconds spent in each state.
`final_component_states` is the health map of the last sample. The report additionally
compresses the samples into `subsystem_timeline` intervals for drawing.

## The assertion context

`MetricsResult.assertion_context()` flattens the metrics into the paths assertions may
reference. This is the complete list. Types: `bool`, `ratio` (0 to 1), `seconds`,
`count`.

| Path | Type | Source |
| ---- | ---- | ------ |
| `flight_control.available` | bool | `safety.flight_control_available` |
| `flight_control.availability` | ratio | `availability.control` |
| `control.availability` | ratio | `availability.control` |
| `safety.loss_of_control` | bool | `safety.loss_of_control` |
| `safety.preserved` | bool | `safety.preserved` |
| `safety.safe_state_reached` | bool | `safety.safe_state_reached` |
| `recovery.mttr` | seconds or null | `recovery.mean_time_to_recovery` |
| `recovery.max` | seconds or null | `recovery.max_time_to_recovery` |
| `recovery.success_rate` | ratio or null | `recovery.success_rate` |
| `recovery.count` | count | `recovery.faults_recovered` |
| `recovery.required` | count | `recovery.faults_requiring_recovery` |
| `recovery.time_to_safe_state` | seconds or null | `recovery.time_to_safe_state` |
| `recovery.<subsystem_with_underscore>` | seconds | `recovery.per_subsystem_max`, only for subsystems that recovered |
| `containment.flight_domain_affected` | bool | `propagation.flight_domain_affected` |
| `containment.critical_domain_reached` | bool | `propagation.critical_domain_reached` |
| `containment.contained` | bool | `propagation.contained` |
| `containment.boundary_crossed` | bool | `propagation.boundary_crossed` |
| `containment.affected_domains` | count | number of `propagation.affected_domains` |
| `containment.affected_components` | count | number of `propagation.affected_components` |
| `containment.propagated_components` | count | number of `propagation.propagated_components` |
| `containment.propagation_depth` | count | `propagation.max_propagation_depth` |
| `mission.completion` | ratio | `mission.completion` |
| `mission.continuity` | ratio | `mission.continuity` |
| `mission.completed` | bool | `mission.completed` |
| `mission.duration` | seconds | `mission.duration` |
| `navigation.integrity` | ratio | `availability.navigation_integrity` |
| `navigation.availability` | ratio | `availability.navigation` |
| `communications.availability` | ratio | `availability.communications` |
| `compute.availability` | ratio | `availability.compute` |
| `power.availability` | ratio | `availability.power` |
| `time.nominal` | seconds | `modes.time_nominal` |
| `time.degraded` | seconds | `modes.time_degraded` |
| `time.failed` | seconds | `modes.time_failed` |
| `time.total` | seconds | `modes.total` |
| `events.injected` | count | `events.injected` |
| `events.applied` | count | `events.applied` |
| `events.rejected` | count | `events.rejected` |
| `events.observed_effects` | count | `events.observed_effects` |
| `events.recoveries` | count | `events.recoveries` |
| `events.expectations_failed` | count | `events.expectations_failed` |

### Evaluation rules

`evaluate_assertion` (`analysis/assertions.py`) looks the path up in this context:

- a path absent from the context is `not_evaluated` with the explanation
  `metric '<path>' is not available for this run`;
- a path present with value `null` is `failed` with the explanation
  `<path> was never measured during the run` (for example `recovery.mttr < 5s` when
  nothing recovered);
- otherwise the comparison is evaluated. Numeric comparisons use a tolerance of 1e-9 for
  `==` and `!=`; a boolean literal compared with a numeric metric (or the reverse)
  fails; booleans only support `==` and `!=`.

Each `AssertionResult` records the measured value, the expected literal, the operator,
the metric path and a human-readable explanation such as
`measured recovery.mission_compute = 4.9s, expected < 10s`. Durations in explanations
are formatted from the literal's notation, percentages likewise.

## Regression thresholds and comparison

Two other consumers read the metrics in slightly different shapes:

- `reslab regression check` (`packages/cli/reslab_cli/regression.py`) reads
  `report.json` files and builds its own context with `score.total`, `recovery.mttr`,
  `recovery.max`, `recovery.success_rate`, `recovery.time_to_safe_state`,
  `mission.completion`, `mission.continuity`, `control.availability`,
  `navigation.integrity`, `communications.availability`, `compute.availability`,
  `containment.flight_domain_affected`, `containment.affected_domains`,
  `containment.propagation_depth`, `containment.propagated_components`,
  `safety.loss_of_control`, `time.degraded`, `time.failed` and the per subsystem
  recovery maxima. See [development](development.md).
- `GET /api/v1/compare` (`services/api/reslab_api/services/compare.py`) compares the
  stored contexts of two runs and calls a change an improvement or a regression only
  when the metric definition states which direction is better; neutral metrics such
  as `mission.duration` and the event counts are reported as `changed`. Per metric
  tolerances (for example 0.2 s on recovery times, 0.5 percent on ratios) avoid
  flagging noise.

## What the metrics do not tell you

- They are only as good as the adapter's observations. The mock adapter observes every
  component of the topology; the PX4 adapter derives a subset from MAVLink telemetry
  and reports the rest as `UNKNOWN`, which then does not count against availability.
- They say nothing about the physical plausibility of a disturbance. The platform
  measures the consequences of an abstract effect; see [threat model](threat-model.md).
- Recovery time depends on the sampling rate: at 10 Hz the smallest measurable
  recovery is 0.1 s.
- A scenario without bounded injections can never produce a non-trivial recovery time
  for the injected subsystem; use durations when recovery is what you want to measure.

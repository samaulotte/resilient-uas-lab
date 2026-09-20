# Electromagnetic resilience: scope and the consequence profile

Electromagnetic disturbances are a real concern for autonomous systems: several
subsystems can degrade at the same moment, in an order and for durations that depend
on the vehicle's design rather than on any single fault. Resilient UAS Lab supports
testing the system's response to such a transient. It does so with an **abstract
consequence profile**: a declaration of which subsystems degrade, in what way, and for
how long. Nothing else.

This document states exactly what the platform models, exactly what it excludes, and
how to write and read a consequence profile scenario. The scope rule is the same one
that governs the whole project (`SECURITY.md`, `CONTRIBUTING.md`,
[threat model](threat-model.md)).

## What is modelled

A consequence profile answers three questions about a transient, and only these:

1. **Which subsystems experience something?** Any of the 17 components of the topology.
2. **What do they experience?** One of the abstract effects of the fault catalog
   allowed for that subsystem (`intermittent`, `unavailable`, `restart`, `degraded`,
   and so on), or the explicit statement that the subsystem is expected to stay
   `operational`.
3. **When and for how long?** A start time (`at`) and a duration (`duration`) that
   applies to the persistent effects; transient effects (`restart`, `crash`) recover
   on their own.

The profile is expanded into ordinary injection events at load time. From then on the
run is like any other: the adapter realizes the effects, the engine records what the
target does, the analysis measures recovery, containment and safety. The word
"electromagnetic" appears in the scenario's name, description and tags because that
is the class of disturbance the author had in mind; the platform's behavior does not
depend on it.

## What is excluded

The following cannot be expressed in a scenario, are not implemented anywhere in the
code base, and are not accepted as contributions:

- any physical description of a source: transmit power, frequency, bandwidth,
  waveform, modulation, pulse shape, duty cycle of an emitter, polarization;
- antennas, gain, directivity, coupling paths, distance, geometry or orientation
  between a source and the vehicle;
- field strength, energy, susceptibility thresholds, shielding effectiveness, or any
  quantity from which a source could be sized;
- any parameter of a weapon or effector;
- any procedure for producing, aiming or timing a disturbance against a real system.

The schema makes this structural. `ConsequenceProfile` has five fields: `name`, `at`,
`duration`, `effects` (a map from subsystem id to effect or `operational`) and
`description` (text, at most 200 characters). Unknown keys are rejected. The effect
parameters that exist (`period`, `duty_cycle`, `level`, `latency_ms`, `loss_ratio`,
`load`, `restart_time`, `watchdog_time`) describe what the subsystem experiences, and
none of them is available on a profile entry at all: a profile entry is a bare effect.
The model docstring states that no physical source parameter can be expressed here.

Consequently, a report about an electromagnetic scenario says how the autonomy coped
with intermittent navigation sensing, a mission computer restart and a telemetry
outage occurring together. It says nothing about what could cause them, and it cannot
be used to size, tune or plan anything on the source side.

## The starter scenario

`scenarios/em-transient-profile-a.yaml` is the reference example:

```yaml
apiVersion: resilient-uas.dev/v1alpha1
kind: ResilienceScenario

metadata:
  name: em-transient-profile-a
  description: >
    Abstract electromagnetic transient, consequence profile A. The profile only
    describes what subsystems experience during the transient: intermittent
    navigation sensing, a mission computer restart and a telemetry outage,
    while flight control is expected to remain operational. No physical source
    parameter is modelled or accepted (see docs/em-resilience.md).
  version: "1"
  tags: [electromagnetic, consequence-profile, containment]

target:
  adapter: mock
  vehicle: x500

mission:
  type: waypoint
  timeout: 180s

recovery:
  gnss_loss: dead_reckoning
  compute_loss: hold

simulation:
  seed: 99

profile:
  name: em-transient-profile-a
  at: 40s
  duration: 8s
  effects:
    navigation.gnss: intermittent
    mission.compute: restart
    communications.telemetry: unavailable
    flight_control.core: operational

assertions:
  - expression: flight_control.available == true
    severity: critical
  - expression: safety.loss_of_control == false
    severity: critical
  - expression: containment.flight_domain_affected == false
    severity: critical
  - expression: recovery.mission_compute < 10s
    severity: high
  - expression: recovery.success_rate == 1.0
    severity: high
  - expression: mission.completed == true
    severity: medium
```

### How it expands

`ResilienceScenario.expanded_events()` turns the profile into three events, all at
`40s`, executed in order of `(at, id)`:

| Event id | Subsystem | Effect | Duration | Expectations |
| -------- | --------- | ------ | -------- | ------------ |
| `em-transient-profile-a-communications-telemetry` | `communications.telemetry` | `unavailable` | 8 s | none |
| `em-transient-profile-a-mission-compute` | `mission.compute` | `restart` | none (transient) | none |
| `em-transient-profile-a-navigation-gnss` | `navigation.gnss` | `intermittent` | 8 s | `flight_control.core OPERATIONAL within 1s` |

The `operational` entry does not inject anything. It becomes an expectation attached to
the first expanded event in the profile's declaration order (here the GNSS entry, which
appears first in the YAML): the flight core must stay healthy for one second after
the transient begins. Event ids are derived from the profile name and the subsystem id
with dots and underscores replaced by dashes, so they can be referenced in event feeds
and reports like any explicit event. `reslab scenario validate` reports the scenario as
having 3 events, and the API's validation endpoint returns them under
`expanded_events`.

### What the run measures

- **Containment.** Three domains are injected (`communications`, `mission_compute`,
  `navigation`). The estimator degrades with the receiver, the planner and services go
  down with their host. None of this may reach `flight_control` or `actuation`:
  `containment.flight_domain_affected == false` is critical.
- **Safety.** `flight_control.available == true` and `safety.loss_of_control == false`
  are critical; the expectation on the flight core checks the first second directly.
- **Recovery.** The mission computer must be back within 10 s of the restart
  (`recovery.mission_compute < 10s`), and everything that required recovery must have
  recovered (`recovery.success_rate == 1.0`). The telemetry gateway and the GNSS
  receiver are bounded to 8 s, so their recovery time is measured from T+48 s, when
  the disturbance ends, not from T+40 s.
- **Mission.** The mission must complete despite the hold caused by the compute
  restart (`compute_loss: hold`).

On the mock adapter this scenario passes; it is part of the regression set run by CI.

## Writing your own profile

1. Start from the subsystems and effects in the fault catalog
   ([scenario format](scenario-format.md)). Every entry must be an effect allowed for
   that subsystem; a disallowed pair is a validation error
   (`profile.effects.<subsystem>: effect '<x>' is not allowed`).
2. Mark the subsystems you expect to ride through the transient as `operational`. They
   become one-second expectations, which is the earliest evidence you get that the
   protected domain held.
3. Choose `duration` for the persistent behaviors. Transient effects in the same
   profile (`restart`, `crash`) ignore it and recover according to the adapter's model.
4. Combine with explicit `events` if the transient should be preceded or followed by
   something else; a scenario may have both a profile and events.
5. Keep the description about consequences. If a description starts to talk about
   causes, it is out of scope.
6. Write critical assertions on containment and control authority, and recovery
   assertions with budgets that reflect the vehicle you are modelling.

Because a profile is a set of ordinary injections, everything else in the platform
applies unchanged: adapter capabilities are checked before the run (the PX4 adapter,
for example, cannot realize `unavailable` on `communications.telemetry`, so this
scenario as written can only run on the mock), rejected injections are visible, and the
report carries the expanded events.

## Interpreting results

A passing electromagnetic consequence scenario means: given that these subsystems
degraded in this way for this long, the autonomy kept control, confined the damage to
the non-critical domains, recovered within budget and finished the mission. It is
evidence about the response of the system model, or of the simulated flight stack, to
a declared set of consequences.

It is not evidence about exposure to any actual disturbance, about any real
environment, or about any real aircraft. Whether a given vehicle would actually
experience these consequences under some condition is a question the platform does not
ask and cannot answer, by design.

## Where the boundary is enforced

| Place | Enforcement |
| ----- | ----------- |
| Schema (`scenario/model.py`) | `ConsequenceProfile` has no source fields; `extra="forbid"` |
| Fault catalog (`scenario/catalog.py`) | Effects are abstract consequences; the module docstring says they never describe how a disturbance is produced |
| Contribution policy (`CONTRIBUTING.md`) | Contributions that implement, describe or parameterize interference, spoofing, electromagnetic or any other attack technique are not accepted |
| Security policy (`SECURITY.md`) | Requests to add such capabilities are out of scope and declined |
| Documentation | This document, the [threat model](threat-model.md) and the starter scenario's own description |

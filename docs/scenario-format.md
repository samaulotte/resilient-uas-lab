# Scenario format

A scenario is a YAML document with `apiVersion: resilient-uas.dev/v1alpha1` and
`kind: ResilienceScenario`. It is the authoritative, portable representation of a
resilience test. This document is the reference for the format as implemented in
`packages/core/reslab_core/scenario/model.py`, the fault catalog in
`scenario/catalog.py` and the loader in `scenario/loader.py`. The generated JSON Schema
is published at `packages/schemas/scenario.v1alpha1.schema.json`.

The schema is deliberately declarative. A scenario names subsystems, effects, times,
expectations and assertions. It cannot express commands, code, file paths, module names
or anything a loader could execute; see [security model](security-model.md). Alpha
versions of the schema may change incompatibly between minor releases of the software;
every change is listed in `CHANGELOG.md` with a migration note.

## How a document is loaded

The loader applies these rules, in order, before any field is looked at:

1. The text must be at most 256 KiB (`MAX_SCENARIO_BYTES`); files must end in `.yaml`
   or `.yml`.
2. YAML is parsed with a restricted `SafeLoader`: no object construction, no custom
   tags. A `!!python/object` tag is a syntax error, not an instruction.
3. Duplicate mapping keys and non-string keys are rejected.
4. Exactly one YAML document is accepted (empty documents are ignored, a second
   document is an error).
5. The mapping is validated by Pydantic models with `extra="forbid"`: unknown keys are
   errors, strings are stripped, and the resulting model is frozen.

Validation errors are reported as a list of issues with a path into the document
(`events[2].inject.duration`), a message and a code. `reslab scenario validate` prints
them; the API returns them in a 422 response; the studio shows them inline. Every
issue is an error except two advisories described under [Warnings](#warnings).

Every duration in a scenario is a string with an explicit unit. Bare numbers are
rejected on purpose so that `30` can never be misread as seconds or milliseconds.
Accepted forms: `250ms`, `30s`, `4.5s`, `2m`, `1m30s`, `1h`, `1h2m3s`.

## Top-level structure

```yaml
apiVersion: resilient-uas.dev/v1alpha1   # required, must be a supported version
kind: ResilienceScenario                 # required
metadata: {}                             # required
target: {}                               # required
mission: {}                              # optional, defaults apply
recovery: {}                             # optional, defaults apply
simulation: {}                           # optional, defaults apply
profile: {}                              # optional consequence profile
events: []                               # up to 128 events
assertions: []                           # up to 64 assertions
scoring: {}                              # optional
```

A scenario needs at least one event or a consequence profile.

### metadata

| Field | Type | Constraints | Default |
| ----- | ---- | ----------- | ------- |
| `name` | slug | lowercase letters, digits and dashes, max 64 chars, unique in the library | required |
| `description` | text | max 4000 chars | `""` |
| `version` | string | max 32 chars | `"1"` |
| `labels` | map | up to 16 entries, keys `^[a-z][a-z0-9_]{0,31}$`, values max 200 chars | `{}` |
| `tags` | list of slugs | up to 16 | `[]` |

### target

| Field | Type | Constraints | Default |
| ----- | ---- | ----------- | ------- |
| `adapter` | enum | `mock`, `px4-gazebo`, `replay` | required |
| `vehicle` | slug | vehicle model identifier | `x500` |
| `configuration` | map | up to 32 scalar values (number, string of at most 200 chars, boolean); adapter specific | `{}` |

The `replay` adapter cannot be used from a scenario file alone: a run on it needs a
`replay_source_run_id` in the run request, and that source run must be `COMPLETED`.

### mission

| Field | Type | Constraints | Default |
| ----- | ---- | ----------- | ------- |
| `type` | enum | `waypoint`, `hover`, `survey` | `waypoint` |
| `timeout` | duration | between `10s` and `1h`; hard limit for the whole run | `180s` |
| `cruise_speed` | number | greater than 0, at most 30 (m/s) | `6.0` |
| `altitude` | number | 2 to 500 (m) | `30.0` |
| `waypoints` | list | up to 64 entries of `{x, y, z, hold}` with `x`, `y` in [-5000, 5000] m (East, North offsets from the origin), `z` in [1, 500] m, `hold` an optional duration | `[]` |

When `waypoints` is empty the adapter uses a default mission. The mock adapter (and the
PX4 adapter, which reuses the same geometry) flies a survey-like loop of about 560 m:
origin, `(90, 30)`, `(150, 110)`, `(80, 170)` at altitude +10, `(-30, 130)` at
altitude +10, `(-50, 40)`, back to the origin. With explicit waypoints the path is
origin, your waypoints, origin. `hover` yields a two-point path at the origin.

Every event must be scheduled strictly before `mission.timeout`.

### recovery

The recovery policy declares how the target is expected to react. These are
expectations that the platform verifies, never commands it executes. The mock adapter
implements them in its behavioral model; other adapters map them to whatever the
target offers.

| Field | Values | Default | Meaning |
| ----- | ------ | ------- | ------- |
| `gnss_loss` | `dead_reckoning`, `hold`, `land` | `dead_reckoning` | Reaction when GNSS aiding is lost |
| `datalink_loss` | `continue`, `hold`, `rtl` | `continue` | Reaction when the C2 link is lost |
| `compute_loss` | `hold`, `land`, `rtl` | `hold` | Reaction when the mission command path is lost |
| `hold_timeout` | duration | `60s` | Maximum time to hold before escalating to land |
| `max_dead_reckoning` | duration | `90s` | Maximum time to fly without GNSS aiding before holding |

The observable consequences of each policy are described in
[degraded modes](degraded-modes.md).

### simulation

| Field | Constraints | Default |
| ----- | ----------- | ------- |
| `seed` | integer, 0 to 2^32 - 1 | `42` |
| `speed` | 0.1 to 100.0, simulation speed factor | `1.0` |
| `telemetry_rate_hz` | 1.0 to 50.0 | `10.0` |

`seed` and `speed` can be overridden per run (`reslab run --seed --speed`, or the run
request). The values actually used are recorded in the run's provenance. With the
mock adapter the same seed, scenario and speed reproduce identical telemetry.

### events

Each event requests one injection at one simulation time and may declare
expectations that are verified after the injection is applied.

```yaml
events:
  - id: gnss-loss                 # slug, unique within the scenario
    at: 35s                       # simulation time, strictly before mission.timeout
    description: optional text    # max 200 chars
    inject:
      subsystem: navigation.gnss  # component id from the topology
      effect: unavailable         # effect from the fault catalog
      duration: 40s               # optional; omitted means until scenario end
      parameters: {}              # effect specific, up to 8 entries
    expect:                       # up to 8 expectations
      - subsystem: navigation.estimator
        state: DEGRADED           # a component state
        within: 3s                # default 5s
        description: optional text
```

Rules enforced at load time:

- `subsystem` must be one of the 17 component ids and `effect` must be allowed for that
  subsystem by the fault catalog (table below).
- `restart` and `crash` are transient effects: the target recovers on its own, so a
  `duration` is rejected for them. `temporary_disconnect` requires a `duration`.
- Every parameter must be whitelisted for the effect, of the right type (numeric or
  duration string) and within its bounds.
- Event ids are unique. Events are executed in order of `(at, id)`.
- Expectation subsystems must exist in the topology; any state may be expected.

At run time the engine emits an `INJECTION_REQUEST`, calls the adapter, then emits
`INJECTION_APPLIED` or `INJECTION_REJECTED`. Expectations are registered only when the
injection was applied. A bounded injection is cleared when its duration elapses
(`INJECTION_CLEARED`, reason `duration elapsed`); an unbounded persistent injection is
cleared at scenario end (reason `scenario end`). Transient injections clear themselves
when the target returns to a healthy state.

#### Expectation semantics

An expectation is decided by the engine from the component states observed after the
injection, within the `within` window:

- expected state healthy (`NOMINAL` or `OPERATIONAL`): the component must stay healthy
  for the whole window; it fails as soon as it leaves the healthy set and passes when
  the window closes;
- expected state `RECOVERED`: the component must leave the healthy set and return to it
  before the window closes; it passes the moment it returns;
- any other state: it passes the first time exactly that state is observed and fails
  when the window closes without it.

Pending expectations are decided at scenario end as if their window had closed. Each
decision is an `EXPECTATION_RESULT` event with `passed`, `expected_state`, `within` and
`elapsed` in its metadata. Expectation counts feed the `events.expectations_failed`
metric and appear in reports; they are not hard gates by themselves.

### profile

A consequence profile is an abstract description of what several subsystems experience
during one transient. It is expanded into ordinary events at load time. It exists for
[electromagnetic resilience](em-resilience.md) scenarios and carries no field that
could describe a physical source.

```yaml
profile:
  name: em-transient-profile-a
  at: 40s
  duration: 8s
  effects:
    navigation.gnss: intermittent
    mission.compute: restart
    communications.telemetry: unavailable
    flight_control.core: operational
  description: optional text
```

Expansion: every entry with an effect becomes an event with id
`<profile name>-<subsystem with dots and underscores replaced by dashes>`, at
`profile.at`, with `profile.duration` for persistent effects and no duration for
transient ones. Entries marked `operational` become expectations
(`state: OPERATIONAL`, `within: 1s`) attached to the first expanded event. For the
profile above the expanded events, in execution order, are
`em-transient-profile-a-communications-telemetry` (`unavailable`, 8 s),
`em-transient-profile-a-mission-compute` (`restart`) and
`em-transient-profile-a-navigation-gnss` (`intermittent`, 8 s, carrying the
`flight_control.core OPERATIONAL within 1s` expectation). A scenario may combine a
profile with explicit events.

### assertions

Assertions are evaluated during analysis against the metrics of the whole run. They
are the mechanism by which a scenario passes or fails.

```yaml
assertions:
  - expression: flight_control.available == true
    severity: critical            # info, low, medium, high, critical; default medium
    description: optional text
```

The grammar is `path operator literal`:

- `path` is a dotted lowercase identifier whose first segment is one of the known
  namespaces `flight_control`, `safety`, `recovery`, `containment`, `mission`,
  `navigation`, `communications`, `compute`, `control`, `time`, `events`, `power`;
- `operator` is `==`, `!=`, `<`, `<=`, `>`, `>=`;
- `literal` is `true`, `false`, a number, a percentage (`80%`, normalized to `0.8`) or a
  duration (`10s`, normalized to seconds). Booleans only accept `==` and `!=`.

Expressions are parsed at load time, so a typo in the namespace or an unparseable
literal is a validation error. A path in a known namespace that the metrics engine
does not populate is accepted at load time and reported as `not_evaluated` after the
run. The complete list of metric paths is in [metrics](metrics.md).

A `critical` assertion that fails is a hard gate: the benchmark result is `failed`
regardless of the score. If a scenario declares no critical assertion the loader emits
a warning because the benchmark can then never hard-fail. The starter scenarios all
declare three critical assertions: `flight_control.available == true`,
`safety.loss_of_control == false` and `containment.flight_domain_affected == false`.

### scoring

| Field | Constraints | Default |
| ----- | ----------- | ------- |
| `profile` | slug, name of a score profile known to the platform | `default` |

The platform looks the profile up in its database. If it is missing the analysis logs
a warning and falls back to `default`. See [scoring](scoring.md).

## The fault catalog

Effects are abstract consequences. They describe what the target experiences, never
how a disturbance is produced. Eleven effects exist:

| Effect | Persistence | Parameters | Description shown in the UI |
| ------ | ----------- | ---------- | --------------------------- |
| `unavailable` | persistent | none | The function is not provided at all until cleared |
| `intermittent` | persistent | `period` (duration), `duty_cycle` (ratio 0 to 1) | The function alternates between available and unavailable |
| `degraded` | persistent | `level` (ratio 0 to 1, remaining capability) | The function is provided with reduced quality or capacity |
| `erroneous` | persistent | none | The function returns plausible but wrong output |
| `stuck` | persistent | none | The output freezes at its last value |
| `restart` | transient | `restart_time` (duration, adapter hint) | The component restarts and recovers on its own |
| `crash` | transient | `watchdog_time` (duration, adapter hint) | The component fails; a watchdog restarts it later |
| `latency` | persistent | `latency_ms` (number, 0 to 60000) | Added delay on the communication path |
| `packet_loss` | persistent | `loss_ratio` (ratio 0 to 1) | A fraction of messages is dropped |
| `resource_pressure` | persistent | `load` (ratio 0 to 1) | CPU or memory pressure reduces processing capacity |
| `temporary_disconnect` | persistent, duration required | none | The link disappears for a bounded duration |

Which effects a subsystem accepts is fixed by the catalog (`_EFFECTS_BY_COMPONENT`):

| Subsystem | Name | Domain | Trust zone | Healthy state | Allowed effects |
| --------- | ---- | ------ | ---------- | ------------- | --------------- |
| `external.gcs` | Ground Control Station | external | external | NOMINAL | unavailable, temporary_disconnect, latency |
| `communications.c2` | C2 Datalink | communications | external | NOMINAL | unavailable, intermittent, degraded, latency, packet_loss, temporary_disconnect |
| `communications.telemetry` | Telemetry Gateway | communications | mission | NOMINAL | unavailable, intermittent, degraded, latency, packet_loss, temporary_disconnect, restart |
| `mission.compute` | Mission Computer | mission_compute | mission | OPERATIONAL | restart, crash, resource_pressure, degraded, unavailable |
| `mission.planner` | Mission Planner Process | mission_compute | mission | OPERATIONAL | restart, crash, stuck, degraded |
| `mission.services` | Mission Services | mission_compute | mission | NOMINAL | unavailable, degraded, latency, restart |
| `network.companion_link` | Companion Link | mission_compute | mission | NOMINAL | latency, packet_loss, temporary_disconnect, unavailable, degraded |
| `security.gateway` | Command Gateway | flight_control | flight_critical | OPERATIONAL | unavailable, degraded, restart, latency |
| `navigation.gnss` | GNSS Receiver | navigation | flight_critical | NOMINAL | unavailable, intermittent, degraded, erroneous, stuck |
| `navigation.estimator` | Navigation Estimator | navigation | flight_critical | NOMINAL | degraded, erroneous |
| `sensors.barometer` | Barometer | navigation | flight_critical | NOMINAL | unavailable, intermittent, degraded, erroneous, stuck |
| `sensors.magnetometer` | Magnetometer | navigation | flight_critical | NOMINAL | unavailable, intermittent, degraded, erroneous, stuck |
| `sensors.imu` (critical) | Inertial Measurement Unit | flight_control | flight_critical | NOMINAL | degraded, erroneous, intermittent |
| `flight_control.core` (critical) | Flight Core | flight_control | flight_critical | OPERATIONAL | degraded, restart, resource_pressure |
| `actuation.motors` (critical) | Motors and ESCs | actuation | flight_critical | OPERATIONAL | degraded, intermittent |
| `power.battery` | Battery | power | flight_critical | NOMINAL | degraded, erroneous, intermittent |
| `power.bus` | Power Distribution | power | flight_critical | NOMINAL | degraded, intermittent |

Injecting into a critical component is allowed but the loader warns that the scenario
deliberately targets the protected domain. The catalog is exposed at
`GET /api/v1/system` (`catalog` and `effects`) and drives the fault library in the
studio. Adapters may support a subset of it; the engine checks the adapter's
capabilities before the run starts and fails the run with an `unsupported_injection`
event if any injection cannot be realized.

## Warnings

Two advisories are produced by `scenario_warnings` and shown by `reslab scenario
validate`, the API validation endpoint and the studio. They never block execution.

| Code | Condition |
| ---- | --------- |
| `flight_critical_target` | An event (explicit or expanded from a profile) injects into `sensors.imu`, `flight_control.core` or `actuation.motors` |
| `no_critical_assertion` | The scenario declares no assertion with severity `critical` |

## Content hash and canonical form

Every scenario has a content hash, `sha256:` followed by the SHA-256 of the canonical
JSON of the validated model (`scenario_content_hash`). Comments, key order and
whitespace do not change the hash; any semantic change does. The hash is stored with
the run, written into the report's provenance and used by the comparison view to tell
whether two runs executed the same document. `scenario_to_yaml` produces the canonical
YAML that runners execute and that reports embed under `scenario.document`.

## Identifiers

| Kind | Pattern |
| ---- | ------- |
| Scenario name, tag, event id, profile name | `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$` |
| Subsystem id | `^[a-z][a-z0-9_]{0,31}\.[a-z][a-z0-9_]{0,31}$`, and must exist in the topology |
| Parameter and label key | `^[a-z][a-z0-9_]{0,31}$` |

## The starter library

Seven scenarios ship under `scenarios/`. All of them target the mock adapter, pass
in-process (`scripts/run_scenarios_local.sh`) and are checked by the regression step
of the `CI` workflow.

| Scenario | Events | Assertions | What it tests |
| -------- | ------ | ---------- | ------------- |
| `compound-degradation` | 3 | 6 | GNSS loss at 30 s, C2 loss at 45 s, mission computer restart at 60 s; containment and recovery under sequential degradation. This is the demo scenario |
| `gnss-loss` | 1 | 6 | GNSS unavailable for 40 s at 35 s; graceful degradation to dead reckoning, prompt re-acquisition |
| `datalink-loss` | 3 | 5 | C2 latency (900 ms), then 40 percent packet loss, then complete loss; local autonomy takes over |
| `sensor-failure` | 2 | 5 | Erroneous barometer, stuck magnetometer; the estimator rejects faulty sensors |
| `mission-compute-restart` | 1 | 6 | Companion computer restart at 40 s with a 6 s recovery budget |
| `resource-pressure` | 2 | 5 | 85 percent load on the mission computer for 50 s, then a services outage; mission continuity |
| `em-transient-profile-a` | 3 (expanded from a profile) | 6 | Abstract electromagnetic consequence profile: intermittent GNSS, mission computer restart, telemetry outage, flight control expected operational |

A new starter scenario is welcome when it tests a behavior the existing seven do not
(see `CONTRIBUTING.md`).

## A complete example

`scenarios/datalink-loss.yaml` shows bounded injections with parameters:

```yaml
apiVersion: resilient-uas.dev/v1alpha1
kind: ResilienceScenario

metadata:
  name: datalink-loss
  description: >
    The C2 datalink degrades (latency, then packet loss) before being lost
    completely. Local autonomy must take over and the mission must complete
    without ground supervision.
  version: "1"
  tags: [communications]

target:
  adapter: mock
  vehicle: x500

mission:
  type: waypoint
  timeout: 180s

recovery:
  datalink_loss: continue

simulation:
  seed: 11

events:
  - id: c2-latency
    at: 20s
    inject:
      subsystem: communications.c2
      effect: latency
      duration: 15s
      parameters:
        latency_ms: 900
  - id: c2-packet-loss
    at: 35s
    inject:
      subsystem: communications.c2
      effect: packet_loss
      duration: 10s
      parameters:
        loss_ratio: 0.4
  - id: c2-loss
    at: 50s
    inject:
      subsystem: communications.c2
      effect: unavailable
    expect:
      - subsystem: mission.compute
        state: OPERATIONAL
        within: 1s

assertions:
  - expression: flight_control.available == true
    severity: critical
  - expression: safety.loss_of_control == false
    severity: critical
  - expression: containment.flight_domain_affected == false
    severity: critical
  - expression: compute.availability == 1.0
    severity: high
    description: Losing the ground link must not disturb onboard compute
  - expression: mission.completed == true
    severity: medium
```

## Tooling

- `reslab scenario validate <files>`: offline validation with warnings; exit code 2 on
  any invalid file.
- `reslab scenario list [--local <dir>]`: the platform library, or the YAML files of a
  directory.
- `reslab scenario show <name>`: the raw document of a library scenario.
- `POST /api/v1/scenarios/validate`: returns `valid`, `issues`, `warnings`, the parsed
  scenario, the canonical YAML, the content hash and the expanded events.
- `POST /api/v1/scenarios` stores a user scenario (`overwrite: true` to replace);
  library scenarios seeded from `scenarios/` cannot be deleted through the API.

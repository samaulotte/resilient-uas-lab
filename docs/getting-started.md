# Getting started

This guide takes you from a clone of the repository to a completed resilience run with
a report, first without any infrastructure (the in-process mock), then with the full
platform in Docker Compose. Nothing here requires a flight stack or hardware. The PX4
simulation profile is covered separately in [PX4 integration](px4-integration.md).

## What you get

A run executes a scenario against a target and produces:

- a stream of classified events (requested, applied, observed, response, recovery);
- normalized telemetry at the configured rate;
- metrics, assertion results and a resilience score;
- `report.json` (schema `1.0`) and a standalone `report.html`.

The default target is the mock adapter: a deterministic component-state simulation of
a multirotor with a companion computer. Its data is labelled
`mock simulation (no flight stack, no hardware)` in every report and `Mock simulator`
in the user interface. It is a model, not a flight controller; treat its numbers as a
way to exercise scenarios and the analysis pipeline, not as a statement about any real
aircraft.

## Prerequisites

| Tool | Version | Needed for |
| ---- | ------- | ---------- |
| Python | 3.12 | everything in Python |
| uv | as pinned in CI (`0.8.17`) | Python workspace and the `reslab` command |
| Docker Engine with Compose v2 | recent | the platform stack |
| Node.js and pnpm | 22 and 10 | only for web development; the Compose build installs its own |
| GNU Make | any | convenience targets (optional) |

## Step 1: the in-process mock, no platform

Install the Python workspace and validate the starter scenarios:

```bash
git clone <repository url>
cd resilient-uas-lab
uv sync --all-packages
uv run reslab --version
uv run reslab scenario validate scenarios/*.yaml
```

`reslab --version` prints `reslab 0.2.0 (scenario API resilient-uas.dev/v1alpha1)`.
The validation output lists every file with its name, number of events and assertions
and the first characters of its content hash, for example:

```
VALID   scenarios/gnss-loss.yaml  gnss-loss v1, 1 events, 6 assertions, sha256:c9386c00a2d3
```

Now execute a scenario in-process. `--local` runs the mock adapter inside the CLI
process; no database, bus or object store is involved. The default speed is 50 times
real time, so a 180 s mission takes a few seconds:

```bash
uv run reslab run scenarios/gnss-loss.yaml --local
```

The command streams the interesting events and prints the summary. This is the output
of that command in this release (mission time is `T+MM:SS`):

```
gnss-loss on the mock adapter (in-process, speed 50.0x, seed 7)
T+00:00  MISSION            Mission 'gnss-loss' started on adapter 'mock'
T+00:13  MISSION            Takeoff complete at 30 m
T+00:28  MISSION            Waypoint 1 reached
T+00:35  INJECTION_APPLIED  GNSS Receiver: 'unavailable' applied via mock:component-state-model
T+00:35  OBSERVED_EFFECT    GNSS Receiver NOMINAL -> UNAVAILABLE: injected unavailable
T+00:35  OBSERVED_EFFECT    Navigation Estimator NOMINAL -> DEGRADED: dead reckoning: GNSS aiding lost
T+00:48  MISSION            Waypoint 2 reached
T+01:05  MISSION            Waypoint 3 reached
T+01:15  RECOVERY           GNSS Receiver UNAVAILABLE -> NOMINAL (after 40.0s)
T+01:15  RECOVERY           Navigation Estimator DEGRADED -> NOMINAL (after 40.0s)
T+01:27  MISSION            Waypoint 4 reached
T+01:43  MISSION            Waypoint 5 reached
T+01:54  MISSION            Waypoint 6 reached
T+01:54  MISSION            All waypoints reached, landing
T+02:14  MISSION            Landed
T+02:14  MISSION            Mission complete

  Result                   PASSED  (score 98.5 / 100)
  Mission                  COMPLETE
  Faults injected          1 (applied 1)
  Critical failures        0
  Recovered subsystems     2
  Degraded transitions     1
  Loss of control          NO
  Safety preservation      PASS
  Fault containment        PASS
  Mean time to recovery    100ms
  Affected domains         1 / 7
```

Two things in this output are worth noticing. The `INJECTION_APPLIED` line is the
adapter confirming the effect, and the two `OBSERVED_EFFECT` lines are what the target
then did: the GNSS receiver went `UNAVAILABLE` (the injected subsystem) and the
estimator went `DEGRADED` (propagation along the topology). The mean time to recovery
is 100 ms, not 40 s: recovery time is measured from the end of the disturbance window
(the injection was cleared at T+01:15 after its 40 s duration) to the return to a
healthy state. The 40 s is the `fault_duration`. See [metrics](metrics.md) for the
precise definitions.

The exit code is 0 when the benchmark result is `passed` and 1 otherwise, which makes
`reslab run --local` usable in CI.

Reports are written under `artifacts/local-runs/<run_id>/` by default (`--output`
changes the directory):

| File | Contents |
| ---- | -------- |
| `report.json` | Canonical report, schema `1.0` |
| `report.html` | Standalone HTML report (inline styles and SVG, no scripts) |
| `events.json` | Every run event |
| `scenario.yaml` | The document exactly as executed |
| `mock-adapter.log`, `mock-injections.json` | Artifacts produced by the mock adapter |

Open `report.html` in a browser to see the summary, score breakdown, assertions,
subsystem state timeline, trajectory, recovery records and event timeline.

## Step 2: the full platform

Copy the environment file and start the stack. Every variable has a working default
for a local demo; change the credentials before exposing the deployment to anyone else
(see [deployment](deployment.md)).

```bash
cp .env.example .env
docker compose up --build -d
```

The first build compiles two images (the Python service image, used by `api`,
`orchestrator`, `runner` and `migrate`, and the web image). Then open Mission Control
at http://localhost:8080. Readiness can be checked with:

```bash
curl -s http://localhost:8080/readyz
```

which returns `{"status":"ready", ...}` once the database, bus and artifact store are
reachable. `docker compose ps` shows every service with its health.

### The Mission Control tour

- **Mission Control** shows the live run: a digital twin of the vehicle following the
  planned path, the blast radius over the topology, the subsystem state timeline, the
  event feed and the system panel. The toolbar has a `Run demo scenario` button that
  queues `compound-degradation` on the mock adapter at the speed selected in the
  toolbar (1x, 2x, 5x or 10x). At 10x the run takes about a minute. The header shows
  `PLATFORM NOMINAL` when the database, bus and artifact store are healthy and at least
  one runner is online, `NO RUNNER ONLINE` when none is, `PLATFORM DEGRADED` when a
  component is unhealthy, and `API UNREACHABLE` when the API cannot be reached.
- **Scenarios** lists the library seeded from `scenarios/` and opens the studio, which
  validates the document against the schema and the fault catalog as you type and
  shows the expanded timeline.
- **Runs** is the history. A run's detail page has Overview, Replay, Events, Metrics,
  Artifacts, Provenance and Scenario tabs.
- **Compare** puts two completed runs side by side with per-metric verdicts.
- **Reports** lists completed runs and shows their canonical report.
- **System** shows versions, component health, adapters and runners with their
  heartbeat, the topology and trust boundaries, score profiles, the fault catalog and
  the effect descriptors. The same data is at `GET /api/v1/system`.
- **Settings** holds browser-local preferences (demo speed, telemetry refresh rate,
  camera mode, whether `LOG` events are shown, reduced motion) and the connection
  details, including links to the OpenAPI documentation.

### The same run from the command line

The CLI talks to the platform through the gateway (`--api`, or `RESLAB_API_URL`;
default `http://localhost:8080`).

```bash
uv run reslab system
uv run reslab scenario list
uv run reslab run compound-degradation --speed 10
```

`reslab run <name>` queues a library scenario by name; `reslab run <path>` submits a
file. With `--wait` (the default) the command follows the run, prints the events as
they arrive, then the summary and the URL of the HTML report. `--no-wait` returns after
queuing. `--adapter` overrides the scenario's adapter (`mock` or `px4-gazebo`), `--seed`
and `--speed` override the simulation parameters, `--label` attaches a free-text label.

Afterwards:

```bash
uv run reslab report <run_id>                       # summary
uv run reslab report <run_id> --json                # raw report.json
uv run reslab report <run_id> -o report.json --html report.html
uv run reslab compare <baseline_run_id> <candidate_run_id>
```

`reslab compare` exits with 1 when the verdict is `regression` or `mixed`.

### The REST API directly

Everything the UI and the CLI do goes through `/api/v1`. Interactive documentation is
at http://localhost:8080/api/docs. For example:

```bash
curl -s -X POST http://localhost:8080/api/v1/runs \
  -H 'Content-Type: application/json' \
  -d '{"scenario_name": "gnss-loss", "speed": 10, "label": "first run"}'
```

returns 202 with the run detail, including its `id`. Then:

```bash
curl -s http://localhost:8080/api/v1/runs/<run_id>
curl -s http://localhost:8080/api/v1/runs/<run_id>/events
curl -s http://localhost:8080/api/v1/runs/<run_id>/report
```

Live updates are available on `ws://localhost:8080/api/v1/runs/<run_id>/stream`; the
frame types are documented in [architecture](architecture.md) and typed in the OpenAPI
document under `x-websocket`.

## Step 3: write your own scenario

Copy a starter scenario and change the events. The document below is
`scenarios/mission-compute-restart.yaml`:

```yaml
apiVersion: resilient-uas.dev/v1alpha1
kind: ResilienceScenario

metadata:
  name: mission-compute-restart
  description: >
    The companion computer restarts while the vehicle is enroute. The flight
    core must hold position autonomously, the mission planner must come back
    and the mission must resume within the recovery budget.
  version: "1"
  tags: [compute, recovery]

target:
  adapter: mock
  vehicle: x500

mission:
  type: waypoint
  timeout: 180s

recovery:
  compute_loss: hold
  hold_timeout: 30s

simulation:
  seed: 5

events:
  - id: mission-compute-restart
    at: 40s
    inject:
      subsystem: mission.compute
      effect: restart
    expect:
      - subsystem: flight_control.core
        state: OPERATIONAL
        within: 1s
      - subsystem: mission.compute
        state: RECOVERED
        within: 10s

assertions:
  - expression: flight_control.available == true
    severity: critical
  - expression: safety.loss_of_control == false
    severity: critical
  - expression: containment.flight_domain_affected == false
    severity: critical
  - expression: recovery.mission_compute < 6s
    severity: high
    description: Restart budget for the companion computer
  - expression: recovery.success_rate == 1.0
    severity: high
  - expression: mission.completed == true
    severity: medium
```

Validate and run it locally, then submit it to the platform:

```bash
uv run reslab scenario validate my-scenario.yaml
uv run reslab run my-scenario.yaml --local
uv run reslab run my-scenario.yaml
```

Which subsystems accept which effects, what the durations mean, how expectations are
verified and which metric paths assertions may use is in
[scenario format](scenario-format.md). The vocabulary of states and events is in
[resilience model](resilience-model.md).

## Step 4: regression checks in CI

`scripts/run_scenarios_local.sh` executes every starter scenario in-process and writes
the reports under `artifacts/reports`; `reslab regression check` compares them against
thresholds and, optionally, a baseline set of reports:

```bash
scripts/run_scenarios_local.sh artifacts/reports
uv run reslab regression check --candidate artifacts/reports --thresholds regression-thresholds.yaml
```

The check exits with 0 only when every scenario passes. This is exactly what the `CI`
workflow does on every push. Details are in [development](development.md).

## Stopping and cleaning up

```bash
docker compose down                 # containers removed, volumes kept
docker compose down -v              # also removes database, bus and artifact volumes
```

## Where things can go wrong

- `Bind for 127.0.0.1:8080 failed: port is already allocated` when the gateway starts:
  another program listens on 8080 (`lsof -nP -iTCP:8080 -sTCP:LISTEN` shows which).
  Either stop it or set `RESLAB_GATEWAY_PORT=8090` (any free port) in `.env` and run
  `docker compose up -d` again; Mission Control is then at that port and the CLI needs
  `--api http://localhost:8090`.
- `command not found: uv`: the `reslab` command and the in-process mock need
  [uv](https://docs.astral.sh/uv/getting-started/installation/) (`brew install uv` on
  macOS, or the upstream install script). The Docker demo does not need it: press
  **Run demo scenario** in Mission Control, or `make demo` falls back to a plain API
  call when uv is absent.
- `cannot reach the API at http://localhost:8080`: the stack is not up, or the gateway
  port was changed (`RESLAB_GATEWAY_PORT`). Pass `--api` or use `--local`.
- A run stays `QUEUED` and then fails with `no runner accepted the job within 300s`:
  no online runner offers the requested adapter. Check `reslab system` (the `Online`
  column) or the System page. The `px4-gazebo` adapter needs the `sim` profile.
- A run fails immediately with `adapter does not support: ...`: the scenario asks for
  an effect on a subsystem that the chosen adapter cannot realize. The PX4 adapter
  supports a subset of the catalog; see [PX4 integration](px4-integration.md).
- `reslab run --local` refuses scenarios whose `target.adapter` is not `mock`: local
  execution is mock only. Use `--adapter mock` to override for a quick check.

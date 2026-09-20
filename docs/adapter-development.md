# Adapter development

An adapter connects the platform to a target system. The control plane never
understands PX4, ArduPilot or ROS 2 internals; it speaks to every target through the
`AutonomousSystemAdapter` contract in `packages/core/reslab_core/adapter.py`. An
adapter translates the generic effects of the fault catalog into whatever mechanism the
target offers and reports back normalized telemetry, component states and events.

This document describes the contract, the models it exchanges, how the engine drives an
adapter, how to register one and what the platform expects of it. The three shipped
adapters (`adapters/mock`, `adapters/px4-gazebo`, `adapters/replay`) are the reference
implementations; the mock adapter is the most complete and is the best starting point.

Adapters targeting real hardware are outside the scope of this repository
(`CONTRIBUTING.md`). Every `data_origin` string in this code base says so explicitly.

## The contract

```python
class AutonomousSystemAdapter(ABC):
    """Lifecycle: prepare -> start -> (observe / inject / clear / health)* -> stop
    -> collect_artifacts."""

    @property
    @abstractmethod
    def capabilities(self) -> AdapterCapabilities: ...

    @abstractmethod
    async def prepare(self, configuration: AdapterConfiguration) -> PlannedPath:
        """Load the mission into the target and return the planned path."""

    @abstractmethod
    async def start(self) -> None:
        """Arm and start the mission. Simulation time starts at zero."""

    @abstractmethod
    async def inject(self, request: InjectionRequest) -> InjectionResult:
        """Apply an effect. Must never raise for unsupported effects; return applied=False."""

    @abstractmethod
    async def clear(self, request: ClearRequest) -> InjectionResult:
        """Remove a previously applied persistent effect."""

    @abstractmethod
    def observe(self) -> AsyncIterator[Observation]:
        """Stream observations at the configured telemetry rate until the mission ends."""

    @abstractmethod
    async def health(self) -> HealthReport:
        """Current component states."""

    @abstractmethod
    async def snapshot(self) -> Snapshot:
        """Full state for diagnostics and replay checkpoints."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the target and release resources. Idempotent."""

    @abstractmethod
    async def collect_artifacts(self) -> list[ArtifactBlob]:
        """Return logs and other artifacts produced by the target."""
```

All methods are coroutines except `capabilities` (a property) and `observe` (an async
generator). Every model exchanged is a frozen Pydantic model.

### Capabilities

```python
class AdapterCapabilities(BaseModel):
    name: str
    kind: AdapterKind  # simulation | hitl | replay
    description: str
    vehicles: tuple[str, ...]
    supported_effects: dict[str, tuple[Effect, ...]]  # keyed by subsystem id
    deterministic: bool  # same seed and scenario reproduce the run
    real_time_capable: bool = True
    data_origin: str  # shown in the UI and written into reports
```

`supported_effects` is the adapter's truthful statement of what it can realize. Before
a run starts the engine checks every expanded event of the scenario against it
(`capabilities.supports(subsystem, effect)`) and fails the run at once with an
`INJECTION_REJECTED` event of severity `critical` (`event_type`
`unsupported_injection`) listing every unsupported pair. It is therefore better to
under-declare than to over-declare. The mock adapter declares the whole catalog; the
PX4 adapter declares the subset in its `mapping.py`.

`data_origin` is copied into the run's provenance and into `report.json`
(`target.data_origin`). It must say where the data comes from so that a reader can never
mistake a simulation for a flight. Existing values:

- `mock simulation (no flight stack, no hardware)`
- `PX4 SITL simulation (software in the loop, no hardware)`
- `replay of a recorded run (no live target)` (the replay adapter appends the source)

### Configuration

`prepare` receives everything the adapter may need:

```python
class AdapterConfiguration(BaseModel):
    run_id: str
    target: Target  # adapter name, vehicle, adapter-specific scalar configuration
    mission: Mission  # type, timeout, cruise speed, altitude, waypoints
    recovery: RecoveryPolicy  # declared reactions to GNSS, datalink and compute loss
    simulation: (
        SimulationConfig  # seed, speed, telemetry_rate_hz (seed and speed already overridden)
    )
    topology: SystemTopology
```

`target.configuration` is the only free-form input a scenario can give an adapter. It
is a map of at most 32 scalar values (numbers, booleans, strings of at most 200
characters). An adapter must validate what it reads from it and ignore what it does not
understand. It must never interpret a value as a path, a command or code.

The returned `PlannedPath` (origin, waypoints in a local East-North-Up frame, optional
safe zone) is stored with the run, drawn in Mission Control and in the HTML report, and
sent to WebSocket clients in the first lifecycle message.

### Injections

```python
class InjectionRequest(BaseModel):
    scenario_event_id: str
    subsystem: str
    effect: Effect
    duration: float | None  # seconds; None means until cleared
    parameters: dict[str, float | int | str]


class InjectionResult(BaseModel):
    applied: bool
    mechanism: str  # how the effect was realized, for traceability
    detail: str = ""
```

`inject` must never raise for an effect it cannot perform: it returns
`applied=False` with a `detail` that says why. The engine records the result as an
`INJECTION_APPLIED` or `INJECTION_REJECTED` event carrying `mechanism` and `detail`, and
only registers the event's expectations and scheduled clear when the injection was
applied. Nothing is silently assumed: a rejected injection is visible in the event
feed, in `metrics.events.rejected` and in the report summary (`faults_applied` versus
`faults_injected`).

`mechanism` should identify the concrete means used, for example
`mock:component-state-model`, `px4:failure sensor_gps off` or `companion:link_restart`.

For a bounded persistent effect the engine calls `clear` when the duration elapses; for
an unbounded one it calls `clear` at scenario end. For transient effects (`restart`,
`crash`) the engine never calls `clear`: the adapter is expected to return the
component to a healthy state on its own, at which point the engine forgets the
injection. The `parameters` for transient effects (`restart_time`, `watchdog_time`) are
hints an adapter may use to time that recovery.

### Observations

`observe` yields one `Observation` per telemetry sample until the mission ends:

```python
class Observation(BaseModel):
    sample: TelemetrySample
    state_changes: tuple[ComponentStateChange, ...] = ()
    responses: tuple[SystemResponse, ...] = ()
    mission_events: tuple[MissionEvent, ...] = ()
    finished: bool = False  # mission finished (complete or aborted)
```

- `sample.t` is the simulation time in seconds and is the clock the engine schedules
  events on. It must be monotonic and start near zero after `start`.
- `sample.health` maps every subsystem the adapter can observe to a `ComponentState`.
  Components the adapter cannot observe should be reported as `UNKNOWN` (or omitted);
  they are excluded from availability metrics instead of counting against them.
- `state_changes` lists the components whose state changed since the previous
  observation, with a short `reason` and, when the adapter knows it, the
  `caused_by` scenario event id. When `caused_by` is absent the engine attributes the
  change to an active injection on the same subsystem or on one of its upstream
  providers in the topology.
- `responses` are autonomous reactions of the target (a failsafe, a mode change, an
  autonomy hand-over). `safe_state=True` marks reactions that put the vehicle in a safe
  state (hold, return, land); they drive the `time_to_safe_state` and
  `safe_state_reached` metrics.
- `mission_events` report progress (`takeoff_complete`, `waypoint_reached`, `landed`,
  and so on) with a `progress` ratio.
- `finished=True` ends the run. The engine then reads `sample.mission.phase`: `COMPLETE`
  means the mission completed, anything else means it ended without completing.

The engine also ends the run when `sample.t` reaches `mission.timeout` or when a
cancellation is requested; in both cases it stops iterating `observe`.

The `TelemetrySample` model (`reslab_core/telemetry.py`) is intentionally independent
of any simulator or middleware message: position in a local ENU frame plus optional
geodetic position, attitude in radians, velocity, `MissionStatus` (phase, progress,
waypoint index), `FlightStatus` (mode, armed, `control_authority`, `autonomy`),
`NavigationStatus` (source, fix, position error, satellites), `CommunicationsStatus`
(links, latency, packet loss), `PowerStatus` and the `health` map. `control_authority`
matters: a single sample with `control_authority=False` counts as loss of control for
the whole run.

### Component states

Adapters report states from the shared vocabulary (`reslab_core/states.py`): `NOMINAL`,
`OPERATIONAL`, `DEGRADED`, `UNAVAILABLE`, `FAILED`, `RECOVERING`, `RECOVERED`,
`UNKNOWN`. Use the healthy vocabulary the topology declares for each component
(`OPERATIONAL` for compute, flight control, actuation and the command gateway,
`NOMINAL` elsewhere); the two are equivalent for every calculation. `RECOVERED` is a
transient label that shows recovery on timelines; the mock adapter reports it for one
sample and then normalizes. The engine treats a transition from an unhealthy state to
any healthy state as a `RECOVERY` event. Definitions are in
[resilience model](resilience-model.md).

### Artifacts

`collect_artifacts` returns `ArtifactBlob` objects (`name`, `content_type`, `data`,
`description`). Names must match `^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,127})$` with no path
separators; the platform validates them again before storing under
`runs/<run_id>/<name>`. Blobs larger than 4 MiB are dropped by the runner with a
warning (`MAX_ARTIFACT_MESSAGE_BYTES`), so keep logs bounded. The mock adapter emits
`mock-adapter.log` and `mock-injections.json`; the PX4 adapter `px4-adapter.log` and
`px4-statustext.log`; the replay adapter `replay-source.txt`.

## How the engine drives an adapter

1. `PREPARING`: capability check, then `prepare(configuration)` and one `health()` call
   to seed the initial states.
2. `RUNNING`: `start()`, then iterate `observe()`. For every observation the engine, in
   this order, processes scheduled injections and clears whose time has come, processes
   the observation's state changes, responses and mission events, decides pending
   expectations, buffers the sample, then checks `finished`, the timeout and
   cancellation.
3. While any component is `RECOVERING` the run state is `RECOVERING`; it returns to
   `RUNNING` when none is.
4. At the end the engine flushes pending expectations, clears remaining persistent
   injections, flushes telemetry, moves to `COLLECTING`, calls `collect_artifacts()` and
   `stop()`. Failures in either are recorded as `LOG` events, never raised.

Any exception raised by the adapter outside `inject` and `clear` fails the run with a
`target_failure` event of severity `critical` and the runner reports `outcome=failed`.
Raise `AdapterError` with a message an operator can act on (the PX4 adapter says which
address it tried and how long it waited, and suggests starting the simulation profile).

## Timing

The engine has no clock of its own; it follows `sample.t`. An adapter is responsible
for pacing. The mock and replay adapters pace against wall time so that the requested
speed factor (`configuration.simulation.speed`) holds over long runs, sleeping at most
0.5 s between samples. A simulator with its own real-time clock (PX4 SITL) simply
yields at the telemetry rate and reports wall-clock-derived simulation time. Telemetry
is batched by the engine (0.5 s of simulation time or 200 samples) before it is
published, so per-sample publishing cost is not the adapter's concern.

## Registering an adapter

Four places know adapter names:

1. `AdapterName` in `packages/core/reslab_core/scenario/model.py`, the `Literal`
   accepted by `target.adapter`. Adding a name here changes the scenario schema; run
   `make schemas` and commit the regenerated files under `packages/schemas/`.
2. `ADAPTER_CATALOG` in `packages/core/reslab_core/adapters_catalog.py`: descriptive
   metadata (display name, kind, `status` of `available`, `experimental` or `planned`,
   description, `data_origin`, requirements) shown in the UI and at
   `GET /api/v1/system`. Whether an adapter is actually usable is reported live from
   runner heartbeats, not from this catalog.
3. `FACTORIES` and `capabilities_for` in `services/runner/reslab_runner/adapters.py`.
   Import the adapter package lazily inside the factory so that a runner offering only
   the mock adapter never loads simulator dependencies.
4. `RunCreateRequest.adapter` in `services/api/reslab_api/schemas.py` (the same
   `Literal`), and the runner's `RESLAB_RUNNER_ADAPTERS` setting, which decides which
   runners advertise the adapter.

An adapter is a workspace package (`adapters/<name>/pyproject.toml`, added to
`[tool.uv.workspace].members` and `[tool.uv.sources]` in the root `pyproject.toml`,
and to the runner's dependencies). Pin dependencies exactly, as the existing adapters
do (`mavsdk-grpc==3.17.4`), and add a sentence to the pull request explaining why an
existing dependency does not do the job.

## Testing an adapter

- Unit tests live in `adapters/<name>/tests/` and run with `uv run pytest`. Test the
  adapter without the real target: the PX4 adapter defines a narrow `PX4Link`
  protocol and its tests drive an in-memory fake link
  (`adapters/px4-gazebo/tests/test_px4_adapter.py`), asserting that `prepare`
  uploads the mission and enables failure injection, that rejected injections are
  reported as not applied, and that an unreachable target fails with a clear error.
- `reslab_core.engine.ScenarioEngine` can be driven directly with a collecting sink,
  exactly as `packages/cli/reslab_cli/local.py` does. This gives you end-to-end
  coverage of your adapter through the engine and the analysis pipeline without any
  service.
- The mock pipeline integration suite (`tests/integration`) exercises the runner,
  orchestrator and API with the mock and replay adapters. Add a case there if your
  adapter changes cross-service behavior.
- A test that keeps `supported_effects` honest is worthwhile:
  `test_mapping_is_a_subset_of_the_catalog` in the PX4 tests checks that every declared
  effect is allowed by the fault catalog for that subsystem.

## Expectations of an adapter

From `CONTRIBUTING.md`, an adapter must declare its capabilities truthfully, reject
injections it cannot perform, fail gracefully when the target is unreachable, and report
its `data_origin` so that reports say where the data came from. In addition:

- Do not fabricate states. Report `UNKNOWN` for what you cannot observe.
- Do not accept anything from the scenario that could be a command, a path or code.
  The scenario can only reach you through `target.configuration` scalars and the
  whitelisted effect parameters.
- Keep `stop` idempotent and safe to call after a failure in `prepare`.
- Keep the adapter free of platform dependencies. Adapters depend on `reslab-core`
  only (the PX4 adapter also depends on `reslab-adapter-mock` for the default mission
  geometry); they must not import the database, bus or settings packages. Runner
  settings reach the adapter through its constructor (see `_px4` in the runner's
  adapter registry).
- State clearly, in the adapter's README and in [roadmap](roadmap.md), what has and
  has not been executed against the real target.

## The replay adapter as a special case

The replay adapter (`adapters/replay`) implements the same contract but re-emits a
recording: the normalized telemetry and events of a completed run, loaded from the
platform API (`ApiReplaySource`) or from a JSON file (`FileReplaySource`, the
`recording-<run_id>.json` document served by `GET /api/v1/runs/{id}/recording`).
Injections are accepted with mechanism `replay:recorded` because the effects are
already in the recording; states come from the recorded `health` maps. Replaying a run
through the engine and the analysis pipeline reproduces its metrics, which the
integration suite checks (`test_replay_reproduces_analysis`).

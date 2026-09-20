# PX4 integration

The `px4-gazebo` adapter (`adapters/px4-gazebo/reslab_adapter_px4/`) connects the
platform to PX4 software-in-the-loop (SITL) running with Gazebo. It speaks MAVLink
through MAVSDK-Python, realizes scenario effects with PX4's System Failure Injection
feature and with companion-side mechanisms, and derives component states from PX4
telemetry and health reports. The Compose `sim` profile runs the simulator and a
dedicated runner for it.

## Status: experimental, not executed in this release

Read this before anything else on the page.

- The adapter is marked `experimental` in the adapter catalog and in `GET
  /api/v1/system`.
- Its logic is unit-tested against an in-memory fake link
  (`adapters/px4-gazebo/tests/test_px4_adapter.py`): mission upload and enabling of
  failure injection during `prepare`, rejection of injections PX4 refuses, geodetic
  conversions, and a clear error when the simulator is unreachable.
- **It has not been executed against a real PX4 SITL instance as part of this
  release's verification.** The `sim` profile, the `runner-sim` service and the nightly
  simulation workflow exist and are described below, but no measured PX4 behavior is
  documented here because none has been recorded. Statements about what PX4 does in
  response to an injection are statements about the adapter's mapping and about PX4's
  documented behavior, not observations from this project.
- The simulation workflow is deliberately not a required CI check until the profile
  has proven stable on hosted runners (`.github/workflows/simulation.yml`).

Everything below should be read with that status in mind. When runs against the
simulator have been performed, this section is the place to record what was observed.

## The simulation profile

```bash
cp .env.example .env
docker compose --profile sim up --build -d
```

Two services join the stack (`compose.yaml`):

| Service | Image | Network | Settings |
| ------- | ----- | ------- | -------- |
| `px4-sim` | `px4io/px4-sitl-gazebo`, pinned by digest, overridable with `PX4_SIM_IMAGE` | `simulation` | `HEADLESS=1`, `PX4_SIM_MODEL` (default `gz_x500`), `PX4_GZ_WORLD` (default `default`), `PX4_SIM_SPEED_FACTOR` (default `1`); 4 CPUs and 4 GB limits; 20 s stop grace period |
| `runner-sim` | the Python service image with `SERVICE=runner` | `control`, `simulation`, `observability` | `RESLAB_RUNNER_ID` (default `runner-sim-1`), `RESLAB_RUNNER_ADAPTERS=px4-gazebo`, concurrency 1, `RESLAB_PX4_MAVSDK_ADDRESS` (default `udpout://px4-sim:14580`), `RESLAB_PX4_CONNECTION_TIMEOUT_SECONDS` (default `120`) |

The `simulation` network is internal and contains only these two services: the
simulator is not reachable from the API, the orchestrator or the default runner, and
the simulation runner reaches storage no more than any other runner does. A Linux host
is recommended; the simulator image is multi-gigabyte.

The simulation runner announces itself through heartbeats like any runner. It appears
with `online: yes` for the `px4-gazebo` adapter in `reslab system` and on the System
page once the first heartbeat arrives (within `RESLAB_RUNNER_HEARTBEAT_SECONDS`, 10 s
by default). Until then a run requesting `px4-gazebo` stays `QUEUED` and is failed by
the orchestrator after `RESLAB_QUEUED_TIMEOUT_SECONDS` (300 s).

To run a scenario on the simulator, override the adapter of a library scenario or
write one with `target.adapter: px4-gazebo`:

```bash
uv run reslab run gnss-loss --adapter px4-gazebo --speed 1 --api http://localhost:8080
```

`reslab run --local` cannot use this adapter; local execution is mock only.

## Transport

`transport.py` defines the narrow `PX4Link` protocol the adapter needs: `connect`,
`disconnect`, `set_param_int`, `upload_mission`, `arm_and_start_mission`,
`inject_failure`, `land`, `snapshot` and `version`. `MavsdkLink` implements it with the
`mavsdk-grpc` distribution (pinned `mavsdk-grpc==3.17.4`), imported lazily so that a
runner offering only the mock adapter never loads it. On `connect` it starts one
tracking task per telemetry subscription (position, attitude, velocity, flight mode,
armed, in-air, landed state, battery, GPS info, health, mission progress, status text,
home) and keeps the latest values in a `VehicleSnapshot`; the adapter reads that
snapshot at the telemetry rate.

Connection strings are MAVSDK system addresses. `PlatformSettings` defaults to
`udpin://0.0.0.0:14540` (listen for a PX4 that sends to the runner); the Compose
profile sets `udpout://px4-sim:14580` (connect out to the simulator container). The
adapter waits up to `connection_timeout` for the connection state to become connected
and then for a home position (or a valid global position); if either does not happen it
raises `AdapterError` with the address, the timeout and the hint to start the
simulation profile, and the run fails with a `target_failure` event.

## Preparation and mission

`prepare`:

1. connects to PX4;
2. sets the parameter `SYS_FAILURE_EN` to `1`. PX4 rejects failure injection commands
   unless this parameter is set, and the feature exists for simulation only;
3. waits for the home position;
4. builds the planned path from the scenario's mission using the same geometry as the
   mock adapter (`reslab_adapter_mock.mission.planned_path_for`, the only reason the
   PX4 adapter depends on the mock package), re-anchored at PX4's home position;
5. converts each waypoint from the local East-North-Up frame to latitude and longitude
   with a spherical-earth approximation (`enu_to_geodetic`), and uploads them as
   fly-through mission items at the mission's cruise speed and relative altitude, with
   return to launch after the mission;
6. initializes every component of the topology to `UNKNOWN`.

`start` arms the vehicle and starts the mission; simulation time is measured from that
instant with the wall clock (`time.monotonic`), so `PX4_SIM_SPEED_FACTOR` and the
scenario `speed` are not the same thing: the scenario's `speed` is recorded in
provenance but the adapter itself does not slow or accelerate PX4.

## Effect mapping

`mapping.py` translates `(subsystem, effect)` pairs into one of two mechanism families.

**`failure`**: PX4 System Failure Injection, sent as `MAV_CMD_INJECT_FAILURE` through
the MAVSDK `Failure` plugin with a failure unit and a failure type. Which unit and type
combinations are implemented depends on the PX4 release and the simulator; PX4 rejects
unsupported combinations, and the adapter then reports the injection as not applied
with the detail `PX4 rejected failure injection: ...`. Nothing is silently assumed.
Clearing sends the same unit with type `OK`.

**`companion`**: mechanisms the adapter performs itself in its role of companion
computer, currently limited to dropping and re-establishing its own MAVLink link. PX4
then reacts with its own failsafes (data link loss handling), which is exactly the
behavior a companion restart would trigger.

| Subsystem | Effect | Mechanism | PX4 unit and type, or companion action |
| --------- | ------ | --------- | --------------------------------------- |
| `navigation.gnss` | `unavailable` | failure | `SENSOR_GPS OFF` |
| `navigation.gnss` | `stuck` | failure | `SENSOR_GPS STUCK` |
| `navigation.gnss` | `erroneous` | failure | `SENSOR_GPS WRONG` |
| `navigation.gnss` | `intermittent` | failure | `SENSOR_GPS INTERMITTENT` |
| `navigation.gnss` | `degraded` | failure | `SENSOR_GPS SLOW` |
| `sensors.barometer` | `unavailable`, `stuck`, `erroneous`, `intermittent`, `degraded` | failure | `SENSOR_BARO` with `OFF`, `STUCK`, `WRONG`, `INTERMITTENT`, `SLOW` |
| `sensors.magnetometer` | `unavailable`, `stuck`, `erroneous`, `intermittent`, `degraded` | failure | `SENSOR_MAG` with `OFF`, `STUCK`, `WRONG`, `INTERMITTENT`, `SLOW` |
| `sensors.imu` | `degraded`, `erroneous`, `intermittent` | failure | `SENSOR_GYRO` with `SLOW`, `WRONG`, `INTERMITTENT` |
| `communications.c2` | `unavailable` | failure | `SYSTEM_MAVLINK_SIGNAL OFF` (PX4 declares data link loss and applies `NAV_DLL_ACT`) |
| `communications.c2` | `temporary_disconnect` | failure | `SYSTEM_MAVLINK_SIGNAL OFF`, cleared with `OK` when the duration elapses |
| `communications.c2` | `intermittent` | failure | `SYSTEM_MAVLINK_SIGNAL INTERMITTENT` |
| `external.gcs` | `unavailable` | failure | `SYSTEM_MAVLINK_SIGNAL OFF` (ground station silence is indistinguishable from link loss for the vehicle) |
| `mission.compute` | `restart` | companion | `link_restart`: drop the link, reconnect after `restart_time` (default 5 s) |
| `mission.compute` | `crash` | companion | `link_crash`: drop the link, reconnect after `watchdog_time` (default 2 s) plus 5 s |
| `mission.compute` | `unavailable` | companion | `link_down`: drop the link until cleared, or for the bounded duration |

This is the adapter's whole `supported_effects` declaration. Everything else in the
fault catalog (`communications.telemetry`, `mission.planner`, `mission.services`,
`network.companion_link`, `security.gateway`, `navigation.estimator`,
`flight_control.core`, `actuation.motors`, `power.*`, and effects such as `latency`,
`packet_loss` and `resource_pressure` anywhere) is unsupported. A scenario that asks
for any of them fails before the run starts with an `unsupported_injection` event
listing the offending pairs. Of the starter scenarios, `gnss-loss`, `sensor-failure`,
`datalink-loss`, `mission-compute-restart` and `compound-degradation` use only
supported pairs and are the ones offered by the simulation workflow;
`resource-pressure` and `em-transient-profile-a` cannot run on PX4 as written.

A unit test (`test_mapping_is_a_subset_of_the_catalog`) keeps the mapping within what
the fault catalog allows for each subsystem.

## Component states derived from telemetry

The adapter reports only what MAVLink lets it observe (`_derive_states`):

| Component | Derivation |
| --------- | ---------- |
| `mission.compute` | `RECOVERING` while a companion mechanism holds the link down; `RECOVERED` on the first observation after that; otherwise `OPERATIONAL` while connected |
| `communications.telemetry` | `UNAVAILABLE` while the link is down (companion mechanism or disconnected), else `NOMINAL` |
| `communications.c2` | `UNAVAILABLE` while an injection on `communications.c2` or `external.gcs` is active, else `NOMINAL` |
| `navigation.gnss` | `UNAVAILABLE` on fix type `NO_GPS` or `NO_FIX`; `DEGRADED` on `FIX_2D` or fewer than 6 satellites; else `NOMINAL` |
| `navigation.estimator` | `NOMINAL` when local and global position are healthy; `DEGRADED` when only local position is; `UNAVAILABLE` when neither (once health has been reported) |
| `sensors.magnetometer` | `NOMINAL` when magnetometer calibration health is ok, else `DEGRADED` |
| `sensors.imu` | `NOMINAL` when gyroscope and accelerometer health are ok, else `DEGRADED` |
| `flight_control.core` | `OPERATIONAL` while a known flight mode is reported, else `UNKNOWN` |
| `power.battery` | `DEGRADED` below 20 percent remaining, else `NOMINAL` |
| `sensors.barometer` | Only while an injection on it is active: `UNAVAILABLE` for `unavailable`, `DEGRADED` otherwise; `UNKNOWN` at other times (PX4 health does not report it) |
| `external.gcs`, `mission.planner`, `mission.services`, `network.companion_link`, `security.gateway`, `actuation.motors`, `power.bus` | Always `UNKNOWN` |

While the link is down every component except `mission.compute` and
`communications.telemetry` is `UNKNOWN`, because nothing can be observed.

Consequences for the metrics: `UNKNOWN` components are excluded from availability, so
`compute.availability` on PX4 reflects only `mission.compute`, `communications`
reflects the two links, and `power` reflects the battery alone. `flight_control.core`
is `OPERATIONAL` whenever PX4 reports a flight mode, so the safety metrics can only
observe loss of control through `control_authority`, which is false while the link is
down or the mode is unknown. A companion `restart` therefore also produces samples with
`control_authority=false` while the link is dropped, which the analysis counts as
loss of control; scenarios that restart the companion on PX4 should be read with that
in mind, and this is one of the behaviors that a real run should confirm or lead to a
refinement of the adapter.

## Flight modes, responses and mission progress

- PX4 flight modes map to the platform vocabulary: `TAKEOFF`, `MISSION`, `HOLD`,
  `RETURN_TO_LAUNCH` (as `RTL`), `LAND`, `READY` (as `IDLE`), anything else `UNKNOWN`.
- A mode change is a `SYSTEM_RESPONSE` named `mode_<mode>`; it is a safe-state response
  when the vehicle went from `MISSION` to `HOLD`, `RTL` or `LAND`.
- New STATUSTEXT messages containing `failsafe`, `lost` or `critical` become
  `px4_status` responses (safe state when they mention `failsafe`); the last 200 status
  texts are kept and exported as the `px4-statustext.log` artifact.
- Mission progress is `current / total` mission items; the mission is finished when PX4
  reports all items done, disarmed and not in the air, which produces a `landed`
  mission event and ends the run with phase `COMPLETE`. Position error is reported as
  0.0 because PX4 does not provide an equivalent estimate over this interface.
- `stop` issues a land command if the vehicle is still armed or in the air, then
  disconnects.
- Artifacts: `px4-adapter.log` (connection, mission upload, injections) and
  `px4-statustext.log`.

The adapter is not deterministic (`deterministic: false` in its capabilities): the
same seed does not reproduce a PX4 run.

## The simulation workflow

`.github/workflows/simulation.yml` runs nightly at 02:30 UTC and on demand with a
scenario choice (`gnss-loss` by default, or `sensor-failure`, `datalink-loss`,
`mission-compute-restart`, `compound-degradation`) and a speed input. It frees disk
space on the runner, starts the stack with the `sim` profile and waits for a runner
advertising `px4-gazebo` to appear in `GET /api/v1/system`, executes the scenario with
`reslab run --adapter px4-gazebo`, collects simulator and runner logs, uploads the
artifacts for 30 days and tears the stack down. A failure is a signal to investigate,
not a merge blocker.

## Known limitations

- Not executed against PX4 SITL in this release (see the status section).
- Partial observability: seven components are never observed, the barometer only
  while injected, the flight core only through the presence of a flight mode.
- Companion mechanisms drop the adapter's own link. Samples keep flowing at the
  telemetry rate during a companion restart, but they carry no live PX4 data: states
  are `UNKNOWN` except the mission computer and telemetry gateway, the flight mode is
  `UNKNOWN` and `control_authority` is false, until the link is re-established.
- Simulation time is wall-clock time since arming; `PX4_SIM_SPEED_FACTOR` is a
  simulator setting and is not reflected in the platform's `speed`.
- Recovery policy fields from the scenario (`gnss_loss`, `datalink_loss`,
  `compute_loss`, timeouts) are not translated into PX4 parameters. PX4 applies its own
  failsafe configuration (for example `NAV_DLL_ACT` for data link loss); the platform
  records what it did.
- Waypoint conversion uses a spherical earth; fine for missions of a few hundred
  meters around the home position, not for anything larger.
- Only the `gz_x500` model has been considered; the adapter accepts vehicles `x500`
  and `gz_x500`.

## Upstream references

- PX4 user guide, System Failure Injection (the `failure` command,
  `MAV_CMD_INJECT_FAILURE`, `SYS_FAILURE_EN`): https://docs.px4.io/main/en/debug/failure_injection.html
- MAVSDK documentation, including the Failure plugin and system addresses:
  https://mavsdk.mavlink.io/
- The simulator image used by the profile is the PX4 project's `px4io/px4-sitl-gazebo`
  image, referenced by digest in `compose.yaml` and `.env.example`.

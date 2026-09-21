# PX4 integration

The `px4-gazebo` adapter (`adapters/px4-gazebo/reslab_adapter_px4/`) connects the
platform to PX4 software-in-the-loop (SITL) running with modern Gazebo. It speaks
MAVLink through MAVSDK, injects the effects of degradation through mechanisms whose
result is observable, and derives component states from PX4 telemetry and health
reports. The Compose `sim` profile runs the simulator and a dedicated runner for it.

## Status: executed and validated against live PX4 SITL

This release was validated by running scenarios against a real PX4 SITL instance, not
only against the unit-test fake link. What was measured is recorded here; nothing on
this page is asserted that was not observed.

Environment under test:

| Component | Version |
| --------- | ------- |
| PX4 | v1.18.0-rc1 (flight software 1.18.0, git `fca3df865`) |
| Gazebo | Harmonic (gz-sim 8.15.0) |
| Vehicle model | `gz_x500` (quadrotor) |
| MAVLink library | MAVSDK, `mavsdk-grpc` 3.17.4 |
| Image | `px4io/px4-sitl-gazebo` pinned by digest (see `.env.example`) |

The runner side of the `sim` profile and three scenarios were executed end to end,
both directly through the engine and through the full Compose stack (API, orchestrator,
`runner-sim`, `px4-sim`). Captured reports are in `docs/px4-runs/`. A live Mission
Control capture of a PX4 run is at `docs/assets/px4-mission-control.png`.

| Scenario | Result | Score | Injections applied | Observed on PX4 |
| -------- | ------ | ----- | ------------------ | --------------- |
| `gnss-loss` | passed | 97.4 | 1 | GPS aiding removed, estimator degraded within ~1.5 s, PX4 position failsafe, recovery ~2.4 s after aiding restored |
| `mission-compute-restart` | passed | 82.2 | 1 | Companion link dropped, mission compute recovered ~5.8 s after reconnect, flight domain untouched |
| `compound-degradation` | passed | 74.2 | 3 | GNSS loss then datalink loss then compute restart; GNSS failsafe to LAND, resume to MISSION after aiding restored |

In every case the three critical assertions held (flight control available, no loss of
control, flight domain contained) and no injection was faked: each is an `INJECTION_APPLIED`
event backed by a real parameter change or link action, and the observed effects are
derived from PX4 telemetry.

The simulation workflow (`.github/workflows/simulation.yml`) is deliberately not a
required CI check: the image is multi-gigabyte and a run takes minutes of simulated
flight, so it runs nightly and on demand rather than on every pull request.

## What is observable on this build, and what is not

The single most important finding is that **PX4's `MAV_CMD_INJECT_FAILURE` sensor
injections (GPS, barometer, magnetometer, accelerometer) are accepted by this Gazebo
image but do not change any telemetry the platform can observe**: the GPS keeps
reporting a 3D fix, the EKF health flags stay valid, and no status text is emitted. The
Gazebo sensor pipeline does not honour the failure-injection hook in this build. A
command being accepted is therefore not evidence that an effect occurred, and the
adapter never treats it as such.

The adapter uses mechanisms whose effect was measured to be observable:

| Subsystem and effect | Mechanism | Observed consequence |
| -------------------- | --------- | -------------------- |
| `navigation.gnss` unavailable / degraded | `param`: `EKF2_GPS_CTRL=0`, restored on clear | EKF loses the global position estimate; estimator goes DEGRADED then the position failsafe fires |
| `sensors.barometer` unavailable / erroneous / stuck | `param`: `EKF2_BARO_CTRL=0` | Barometer aiding removed from the EKF height estimate |
| `sensors.magnetometer` unavailable / stuck | `param`: `EKF2_MAG_TYPE=5` (none) | Magnetometer fusion disabled |
| `communications.c2`, `external.gcs` unavailable | `companion`: drop the MAVLink link | PX4 declares data-link loss (`NAV_DLL_ACT`) and returns to launch |
| `mission.compute` restart / crash / unavailable | `companion`: drop and re-establish the link | The companion is gone then returns; PX4 keeps flying the uploaded mission autonomously |

The `param` mechanism removes an aiding source from the estimator: it injects the
*consequence* of a sensor becoming unavailable (the EKF can no longer use it), which is
exactly this project's scope. It never models a physical cause. The original parameter
value is read before injection and restored precisely on clear.

The barometer and magnetometer parameter mechanisms are wired and unit-tested, and the
GNSS parameter mechanism was verified in flight. The barometer and magnetometer effects
were not separately flight-verified in this release; treat their PX4 behaviour as
best-effort until a run is recorded here.

## What stays UNKNOWN

When the adapter cannot observe a component, its state is `UNKNOWN`, never a failure.
This matters for two situations:

- **Before the estimator has converged** (the first second or so after arming), the
  sensor and estimator states are `UNKNOWN` rather than read from settling boot-time
  health flags.
- **While the companion link is down** (mission-compute restart, datalink loss), every
  component the adapter can no longer see becomes `UNKNOWN`. The flight core is not
  reported as failed just because telemetry stopped. `UNKNOWN` is excluded from
  availability, from fault propagation and from the loss-of-control test; a critical
  assertion that cannot be evaluated for lack of observation makes the benchmark
  inconclusive rather than passed (see `docs/metrics.md`).

## Connectivity

The adapter connects on PX4's broadcast GCS link (`udpin://0.0.0.0:14550`) and the
`px4-sim` service is started with `PX4_NET_INTERFACE` set so PX4 broadcasts MAVLink on
the simulation network. Two things were measured that drove this choice:

- On the onboard port (`udpout://...:14580`), a second MAVSDK client that connects after
  the first disconnects is not rediscovered, which breaks any scenario that drops and
  re-establishes the link. On the broadcast link, reconnection works, because PX4 keeps
  broadcasting regardless of whether it is receiving.
- A link drop longer than `COM_DL_LOSS_T` (10 s by default) drives PX4 into
  Return-To-Launch. This is the real data-link-loss failsafe the companion mechanisms
  rely on.

Each connection gets its own `mavsdk_server` port so a reconnect never collides with a
server that has not been reaped yet.

## The simulation profile

```bash
cp .env.example .env
docker compose --profile sim up --build -d
# then run a scenario against the simulator:
uv run reslab run gnss-loss --adapter px4-gazebo --api http://localhost:8080
```

Two services join the stack (`compose.yaml`):

| Service | Image | Network | Notes |
| ------- | ----- | ------- | ----- |
| `px4-sim` | `px4io/px4-sitl-gazebo`, digest-pinned, overridable with `PX4_SIM_IMAGE` | `simulation` | `HEADLESS=1`, `PX4_SIM_MODEL` (default `gz_x500`), `PX4_GZ_WORLD` (default `default`), `PX4_NET_INTERFACE` (default `eth0`), started with `-d`; 4 CPU / 4 GB limits |
| `runner-sim` | the Python service image with `SERVICE=runner` | `control`, `simulation`, `observability` | `RESLAB_RUNNER_ADAPTERS=px4-gazebo`, concurrency 1, `RESLAB_PX4_MAVSDK_ADDRESS` (default `udpin://0.0.0.0:14550`) |

The `simulation` network is internal and contains only these two services: the
simulator is not reachable from the API, the orchestrator or the default runner, and
the simulation runner holds no database or object-store credentials. A Linux host is
recommended; on a host with only two CPUs, lower the `px4-sim` CPU limit.

## Reproducing a validated run

```bash
docker compose --profile sim up --build -d --wait
# wait until the runner advertises the adapter:
curl -s http://localhost:8080/api/v1/system | grep px4-gazebo
uv run reslab run gnss-loss --adapter px4-gazebo --api http://localhost:8080 --wait
uv run reslab report <run-id> --api http://localhost:8080 --html report.html
```

The run's events distinguish the requested injection, the applied injection, the
observed effect and PX4's response, so a report can be read as a causal chain rather
than an assumption. For `gnss-loss` the chain is: `INJECTION_APPLIED navigation.gnss`
(EKF2_GPS_CTRL set to 0) at T+35, `OBSERVED_EFFECT navigation.gnss UNAVAILABLE`,
`OBSERVED_EFFECT navigation.estimator DEGRADED`, `SYSTEM_RESPONSE CRITICAL: Failsafe
activated`, then recovery once the aiding is restored.

## Limitations

- Sensor failure injection through `MAV_CMD_INJECT_FAILURE` is not observable on this
  Gazebo image (measured); the adapter uses EKF aiding parameters instead and does not
  advertise effects it cannot realise.
- `datalink-loss` models progressive link degradation (`latency`, then `packet_loss`,
  then `unavailable`). Link latency and packet loss on the GCS link have no simple
  observable mechanism on this build, so those effects are reported as not applied on
  PX4; only the full link loss is realised. The scenario therefore runs fully on the
  mock adapter and partially on PX4. `sensor-failure` (barometer and magnetometer)
  relies on the parameter mechanisms that were not flight-verified in this release.
- Runs are real-time. The 560 m survey mission plus a failsafe often exceeds a
  scenario's timeout on PX4, so `mission.completion` and `mission.completed` can be
  lower than on the mock. This is a real difference between the mock and the flight
  stack, surfaced in the report rather than hidden.
- The adapter targets simulation only. It never commands real hardware.

## Upstream references

- PX4 SITL with Gazebo: https://docs.px4.io/main/en/sim_gazebo_gz/
- PX4 simulation failure injection: https://docs.px4.io/main/en/debug/failure_injection.html
- PX4 EKF2 configuration (aiding control parameters): https://docs.px4.io/main/en/advanced_config/tuning_the_ecl_ekf.html
- PX4 data-link-loss failsafe (`NAV_DLL_ACT`): https://docs.px4.io/main/en/config/safety.html
- MAVSDK: https://mavsdk.mavlink.io/
- PX4 in Docker: https://docs.px4.io/main/en/test_and_ci/docker.html

# Roadmap

This page separates what release 0.1.0 does from what is planned, so that nobody
mistakes a catalog entry, a settings field or a sentence in a docstring for a working
feature. It lists no dates. Items move from "planned" to "implemented" through the
normal contribution process (`CONTRIBUTING.md`); larger items start with an issue so
that design questions are settled before code is written.

Everything in the "Implemented" section has been verified in this release: unit tests
(Python and web), the mock pipeline integration suite, a healthy Compose stack and the
Playwright end-to-end journey against the gateway. The one exception is called out
explicitly.

## Implemented in 0.1.0

| Area | State |
| ---- | ----- |
| Domain model | Component and run state vocabularies with validated transitions; 17-component multirotor topology with two trust boundaries; closed fault catalog of 11 effects with per-effect parameter whitelists; canonical scenario content hash |
| Scenario schema `resilient-uas.dev/v1alpha1` | Strict loader (restricted YAML, duplicate keys rejected, 256 KiB limit, single document), timeline events, expectations, assertions, mission, recovery policy, simulation parameters, scoring profile name, consequence profile |
| Engine | Deterministic timeline execution, bounded injections, expectation evaluation, cancellation, lifecycle events, telemetry batching |
| Analysis | Availability, weighted navigation integrity, recovery records measured from the end of the disturbance window, topology-based propagation depth, degraded-mode timing, safety metrics, declarative assertion grammar, weighted scoring with hard gates, `report.json` schema `1.0`, standalone `report.html` |
| Adapters | `mock` (whole catalog, deterministic, labelled), `replay` (recorded runs), `px4-gazebo` (MAVSDK transport, PX4 failure injection, companion-side mechanisms; unit-tested with a fake link) |
| Platform | FastAPI control plane with versioned REST API, WebSocket run stream and Prometheus metrics; orchestrator with state management, watchdog and analysis; runner with at-most-once acceptance from a JetStream work queue; PostgreSQL schema with Alembic; S3-compatible artifact store; scenario library seeding |
| Mission Control | Live mission view (digital twin, blast radius, state timeline, event feed, system panel), run history and detail, comparison, scenario library and studio, reports, system and settings pages |
| CLI | `reslab scenario validate/list/show`, `run` (platform or `--local`), `report`, `compare`, `system`, `regression check` |
| Reference deployment | Hardened Compose stack with segmented networks, digest-pinned images, Caddy gateway, optional `sim` and `observability` profiles |
| Continuous integration | Lint, type checks, unit, integration and end-to-end suites, image builds with a non-root check, schema and client drift checks; a security workflow with dependency audits, secret scanning, CodeQL, Dockerfile and image scans and SBOMs; a nightly, on-demand simulation workflow |

**Not verified in this release:** execution of the `px4-gazebo` adapter against a real
PX4 SITL instance. The adapter, the `sim` Compose profile and the simulation workflow
exist and the adapter's logic is unit-tested against an in-memory fake link, but no run
against the simulator has been performed as part of this release's verification. It
is marked `experimental` in the adapter catalog. See
[PX4 integration](px4-integration.md).

## Planned

The following are declared or referenced in the repository but have no implementation.
They are listed in the order in which they are referenced by the code, not by priority.

### Additional adapters

The adapter catalog (`packages/core/reslab_core/adapters_catalog.py`) lists three
entries with status `planned`. They appear on the System page and in
`GET /api/v1/system` so that users see the intended direction; none can be selected in
a scenario (`target.adapter` accepts only `mock`, `px4-gazebo` and `replay`) and no
runner offers them.

| Name | Display name | Kind | Description in the catalog |
| ---- | ------------ | ---- | -------------------------- |
| `px4-hitl` | PX4 hardware-in-the-loop | `hitl` | PX4 flight controller hardware on a bench, simulator providing sensors |
| `ardupilot` | ArduPilot SITL | `simulation` | ArduPilot software-in-the-loop |
| `ros2` | Generic ROS 2 | `simulation` | Generic ROS 2 robot adapter using lifecycle nodes and SROS2 enclaves |

Note on `px4-hitl`: `CONTRIBUTING.md` states that adapters targeting real hardware are
outside the scope of this repository. A bench setup in which the flight controller
hardware is fed by a simulator is the only hardware-adjacent configuration the catalog
anticipates, and whether it belongs in this repository or in a separate one is an open
design question to settle in an issue before any code.

The `AdapterKind` enum already contains `hitl`, and the `Provenance.data_origin`
docstring mentions `hardware-in-the-loop` as a possible value; both are vocabulary,
not features.

### Authentication and authorization

The API description states that authentication is not enforced in the local v0.1
deployment and that the API is designed to sit behind an OIDC-aware gateway. Nothing in
the gateway configuration or the API implements identity yet. The intended shape is
identity at the edge (the gateway) with the API receiving and recording who did what;
recording an actor in run provenance and labels would follow. Until then the
deployment guide asks operators to restrict network access or place an authenticating
proxy in front of port 8080.

### Score profile management

Custom score profiles are fully supported by the analysis (`ScoreProfile`,
`load_score_profile`, lookup by name in the `score_profiles` table) but there is no
API endpoint, CLI command or UI to create or edit them; only the `default` profile is
seeded. Managing profiles through the API and selecting one for a run from the UI is
planned.

### Replay sources

`ReplayRecording` describes its producers as the API export and "future ULog/rosbag
converters". Only the API export (`GET /api/v1/runs/{id}/recording`) and JSON files in
that format exist. Converters from flight-stack logs are not implemented.

### Scenario schema evolution

`v1alpha1` is an alpha version and may change incompatibly between minor releases of
the software. Every change will be listed in `CHANGELOG.md` with a migration note.
Reaching a stable `v1` requires experience from users beyond the starter library. A
non-exhaustive list of things the schema does not yet express: per-waypoint actions
beyond `hold`, several concurrent missions, a `survey` mission type with generated
coverage (the `survey` type is accepted but the adapters treat it like `waypoint` with
the default geometry), and topology selection (every scenario runs against the default
multirotor topology).

### Security hardening beyond the local deployment

Listed in the [security model](security-model.md) as known limitations: TLS at the
gateway, authentication on NATS and PostgreSQL, rate limiting, and content for the
`security/policies` and `security/examples` directories, which are reserved and empty
in this release.

### Simulation profile maturity

The `Simulation (PX4 SITL)` workflow runs nightly and on demand and is explicitly not a
required check "until the profile has proven stable on hosted runners". Promoting it to
a required check, and documenting measured behavior of PX4 under each starter scenario,
depends on that experience.

## Not planned

To avoid repeated discussion, the following are out of scope by design and will not
appear on this roadmap, however the request is phrased:

- modelling how a disturbance is produced: interference, spoofing or jamming
  techniques, sources of electromagnetic energy and their parameters, any weapon or
  effector parameter (see [threat model](threat-model.md) and
  [em-resilience](em-resilience.md));
- adapters that connect to real aircraft, radios or receivers;
- any form of code execution from scenario documents.

## How to influence the roadmap

Open an issue using the feature request or scenario proposal form. Proposals that come
with a scenario in the shared vocabulary of [resilience model](resilience-model.md),
an explanation of what existing scenarios cannot measure, and a note on which adapter
would realize the effects are the easiest to evaluate.

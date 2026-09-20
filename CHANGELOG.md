# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Three artefacts are versioned: the software (this file), the scenario schema
(`apiVersion: resilient-uas.dev/v1alpha1`) and the report schema (`schema_version` in
`report.json`). Schema changes are listed in their own subsections.

## [Unreleased]

### Added

- PX4 SITL integration validated end to end against live PX4 v1.18 with Gazebo Harmonic
  (MAVSDK 3.17.4). `gnss-loss`, `mission-compute-restart` and `compound-degradation` run
  with real injected faults and observed reactions; captured reports are in
  `docs/px4-runs/` and a live capture in `docs/assets/px4-mission-control.png`. The
  `Simulation (PX4 SITL)` workflow now runs a real scenario and fails if PX4 does not
  start, if no fault is applied, or if the benchmark does not pass.

### Changed

- The `px4-gazebo` adapter injects observable effects: GNSS, barometer and magnetometer
  losses remove the aiding source from the EKF (control parameters, restored on clear),
  and command and companion-link losses drop the MAVLink link to trigger PX4's real
  data-link-loss failsafe. It connects on the broadcast GCS link so it can rediscover
  PX4 after a link drop, advertises only the effects it can realise, and leaves
  unobserved components UNKNOWN. This replaces the `MAV_CMD_INJECT_FAILURE` sensor
  mappings, which the reference Gazebo image accepts but does not realise.

### Fixed

- Observability semantics in the metrics engine: an unobserved component (UNKNOWN) is no
  longer counted against flight-control availability, as fault propagation, or as loss of
  control; a metric that was never observed makes its assertion inconclusive rather than a
  silent fail; and a critical assertion that cannot be evaluated makes the benchmark
  inconclusive rather than passed. The live recovery estimate no longer counts a return
  from UNKNOWN as a recovered fault.

## [0.1.0] - 2026-09-20

First public release.

### Added

- Domain model for resilience testing of autonomous systems: component and run state
  vocabularies with validated run transitions, a seventeen-component multirotor topology
  with trust boundaries, a closed fault catalogue of eleven effects with per-effect
  parameter whitelists, and a canonical scenario content hash for provenance.
- Scenario schema `resilient-uas.dev/v1alpha1`: strictly validated declarative YAML
  (restricted loader, duplicate-key rejection, size limit, no code execution) with
  timeline events, expectations, assertions, mission definition and scoring profile.
- Scenario engine: deterministic timeline execution with bounded injections,
  expectation evaluation, cancellation, and lifecycle event emission.
- Analysis: availability, weighted navigation integrity, recovery records measured from
  the end of the disturbance window, topology-based propagation depth (blast radius),
  degraded-mode timing, safety metrics, assertion grammar (`path op literal` with
  booleans, numbers, durations and percentages), weighted scoring with hard gates that
  override the score, and the resilience report (`report.json` schema 1.0 plus a
  standalone `report.html`).
- Adapters: deterministic mock simulation (whole catalogue supported, clearly labelled
  as mock data), PX4 SITL / Gazebo adapter over MAVSDK with graceful failure when the
  simulator is unreachable, and a replay adapter that reproduces recorded runs.
- Platform services: FastAPI control plane with a versioned REST API, WebSocket run
  stream and Prometheus metrics; orchestrator with run state management, a
  progress-aware runner watchdog and report generation; runner executing jobs from a
  NATS JetStream work queue with at-most-once acceptance.
- Persistence: PostgreSQL schema managed by Alembic, S3-compatible artifact store
  (RustFS by default), scenario library seeding.
- Mission Control web application: live mission view with digital twin, blast radius,
  state timeline, event feed and system panel; run history, run detail with metrics,
  assertions, artifacts, replay and provenance; run comparison; scenario library and
  studio with schema validation; system and settings pages.
- `reslab` command line interface: validate, run (platform or in-process), report,
  compare, system, and a resilience regression check for CI with configurable
  thresholds.
- Starter scenario library: `compound-degradation`, `gnss-loss`, `datalink-loss`,
  `sensor-failure`, `mission-compute-restart`, `resource-pressure` and
  `em-transient-profile-a` (an abstract consequence profile; no attack parameters are
  modelled).
- Reference deployment: multi-stage container images running as an unprivileged user
  with read-only root filesystems, a Compose stack with segmented internal networks and
  digest-pinned images, a Caddy gateway, an optional PX4 SITL simulation profile and an
  optional Prometheus / Grafana observability profile.
- Continuous integration: lint, type checks, unit, integration and end-to-end suites,
  image builds and a non-root image check; a security workflow with dependency audits,
  secret scanning, CodeQL, Dockerfile misconfiguration and image vulnerability scans and
  SBOM generation; a nightly, on-demand simulation workflow.
- Documentation: architecture, getting started, scenario format, adapter development,
  resilience, metrics, scoring, trust boundaries, security and threat models, safety and
  degraded-mode models, electromagnetic resilience scope, deployment, development,
  roadmap and PX4 integration guides.

### Scenario schema

- `v1alpha1` introduced. Alpha versions may change incompatibly between minor releases
  of the software; every change will be listed here with a migration note.

### Report schema

- `1.0` introduced.

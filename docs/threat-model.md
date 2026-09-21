# Threat model

This document has two parts that must not be confused.

The first part states what the platform is **for** and, more importantly, what it is
**not for**: the scope line that decides which capabilities are accepted into the code
base. The second part is a conventional threat model **of the platform as software**:
assets, actors, entry points, threats and the controls that answer them, plus the
residual risks of release 0.2.0.

## Part 1: scope of the tool

Resilient UAS Lab simulates the **effects** of degradation on an autonomous system so
that engineers can measure how well the system detects, contains and recovers from
them. A scenario says that a GNSS receiver stops delivering fixes, that a datalink
drops packets, that a mission computer restarts, that several subsystems degrade at
once. It never says how such a thing would be brought about.

### What is in scope

- Declaring consequences on the subsystems of a modelled vehicle: the eleven abstract
  effects of the fault catalog on the seventeen components of the topology.
- Verifying declared expectations and assertions about the system's observable
  response.
- Measuring availability, recovery, containment, safety preservation and mission
  continuity, and comparing runs.
- Driving simulators that offer their own fault injection interfaces (PX4 SITL through
  its System Failure Injection feature, which only works in simulation and only when
  the vehicle's `SYS_FAILURE_EN` parameter is set) and reproducing recorded runs.
- Abstract consequence profiles for transients affecting several subsystems, including
  electromagnetic transients described only by their consequences
  ([em-resilience](em-resilience.md)).

### What is out of scope, permanently

The following are not implemented, not documented and not accepted as contributions,
whatever the stated purpose:

- any technique, procedure or parameter for producing interference, spoofing or
  jamming of radio links, satellite navigation or sensors;
- any model of a source of electromagnetic energy: no transmit power, frequency,
  waveform, antenna, gain, coupling, distance, field strength or susceptibility
  threshold, and no geometry between a source and a vehicle;
- any parameter of a weapon or effector of any kind;
- any interface to real aircraft, real radios or real receivers; adapters targeting
  hardware are outside this repository;
- any code path that lets a scenario execute commands, load modules or reach files.

The scenario schema enforces this structurally: it has no field in which such data
could be expressed, and the consequence profile accepts only a name, a start time, a
duration and a map from subsystem to effect. `CONTRIBUTING.md` and `SECURITY.md`
restate the rule; requests to add such capabilities are declined.

### Why the line is where it is

The platform's value is in the response side: how the autonomy behaves once a
subsystem is degraded. That side is fully expressible with abstract effects, and it is
the same regardless of what caused the degradation. Modelling causes would add nothing
to the measurement while creating material that has no place in an open repository.

## Part 2: threats to the platform

### Assets

| Asset | Why it matters |
| ----- | -------------- |
| Scenario library | Expresses the tests an organization relies on; tampering changes what is measured |
| Run records: events, telemetry, metrics, assertions, scores, reports | The evidence; integrity and provenance are the product |
| Report artifacts in the object store | Distributed to people who did not run the test; must not carry executable content |
| Platform availability | Runs take minutes; a stalled orchestrator or runner pool blocks engineering work |
| Credentials | Database, object store, Grafana admin |
| Host resources | The simulator profile is heavy; runaway runs affect the host |

### Actors and entry points

| Actor | Entry point | Trust in 0.2.0 |
| ----- | ----------- | -------------- |
| Operator using Mission Control or the CLI | Gateway port 8080: REST, WebSocket | Fully trusted; no authentication exists |
| Author of a scenario document | `POST /api/v1/scenarios`, `POST /api/v1/runs` with `document`, files passed to the CLI | Untrusted input, validated |
| Runner process | NATS subjects `reslab.runs.>`, `reslab.runners.heartbeat` | Untrusted worker; messages validated |
| Target system (simulator, recording) | Adapter calls inside the runner | Untrusted; failures are contained in the runner |
| Reader of a report | Downloaded `report.html`, `report.json`, artifacts | Must be protected from stored content |
| Anyone on the host network | Published ports | Only the gateway (and Grafana with the observability profile) |

### Threats and controls

The table uses the usual categories: spoofing, tampering, repudiation, information
disclosure, denial of service, elevation of privilege. "Control" refers to mechanisms
described in the [security model](security-model.md).

| Id | Threat | Category | Control | Residual risk |
| -- | ------ | -------- | ------- | ------------- |
| T1 | A scenario document makes the loader execute code or construct objects | Elevation | Restricted `SafeLoader`, no tags, closed Pydantic schema with `extra="forbid"`, closed effect and adapter vocabularies, declarative assertion grammar; the same loader in CLI, API and runner | Low; a loader bug would be a vulnerability in scope of `SECURITY.md` |
| T2 | A scenario references a file, URL or command through a free-text field | Elevation | No path-like field exists; `target.configuration` is scalars only; adapters treat configuration as opaque | Low, depends on adapter discipline (reviewed) |
| T3 | Oversized or deeply nested documents exhaust the API | Denial of service | 256 KiB scenario limit, 512 KiB body limit (413), bounded list sizes in the schema | Low |
| T4 | Path traversal through run ids or artifact names | Tampering, disclosure | Strict patterns on run ids and artifact names, keys always `runs/<run_id>/<name>`, local store checks resolved paths | Low |
| T5 | A stored HTML report executes script in a reader's browser | Elevation | Renderer emits no script and autoescapes values; served with a CSP forbidding scripts; non-HTML artifacts served as attachments | Low |
| T6 | A compromised or buggy runner forges run state, injects bogus events or floods the bus | Tampering, denial of service | Orchestrator validates every transition against the state machine, ignores messages for terminal runs, re-validates artifact names, caps payloads (8 MiB, artifacts 4 MiB, 500 samples per batch), terminates undecodable messages and bounds retries; unique constraints prevent duplicates | Medium: a runner can still publish plausible but false telemetry for its own run; `data_origin` and provenance make the source visible but do not authenticate it |
| T7 | A runner reaches the database or object store | Elevation | Runners are on the `control` network only and receive no storage settings | Low in Compose; depends on the deployment preserving the network split |
| T8 | A runner dies mid-run and the job is executed twice | Tampering (duplicate evidence) | At-most-once acceptance; the watchdog fails abandoned runs instead of redelivering | Low; the cost is a failed run, not a duplicate |
| T9 | Runs are queued for an adapter nobody offers, or a runner disappears | Denial of service | `queued_timeout_seconds` (300) fails orphaned runs; `runner_stale_after_seconds` (45) fails runs whose runner stopped heartbeating and progressing; per-runner concurrency bounded (1 to 8) | Low |
| T10 | Anyone who can reach the gateway can create, cancel and delete | Spoofing, tampering | None in this release beyond network placement | High for any exposure beyond a trusted network; documented, planned |
| T11 | Default credentials are used in a shared deployment | Spoofing | `.env.example` states they must be changed; internal networks limit reachability | Medium; a deployment responsibility, out of scope for vulnerability reports per `SECURITY.md` |
| T12 | Secrets leak through logs or error responses | Disclosure | `SecretStr` settings, redaction of sensitive keys in structured logs, generic 500 responses | Low |
| T13 | Traffic between browser and gateway is read or altered | Disclosure, tampering | Not addressed by the stack; TLS must be terminated in front of the gateway | Medium until TLS is deployed |
| T14 | Traffic between services (NATS, PostgreSQL, S3) is intercepted | Disclosure | Internal Docker networks, no external route | Medium if the deployment moves services across hosts without adding TLS |
| T15 | Container escape or privilege escalation | Elevation | The project's containers run as an unprivileged user with a read-only root filesystem and all capabilities dropped; every container has `no-new-privileges`, a digest-pinned image and resource limits; no Docker socket, no privileged containers | Low |
| T16 | Supply chain: vulnerable or tampered dependencies and images | Tampering | Exact version pins and lock files (`uv.lock`, `pnpm-lock.yaml`), digest-pinned images and actions, dependency review, `pip-audit`, `pnpm audit`, Trivy, CodeQL, SBOMs, weekly rescans | Medium; inherent to any dependency set |
| T17 | A report is misread as evidence from a real aircraft | Repudiation, misuse | `data_origin` in every report and the UI (`Mock simulator`, `PX4 SITL simulation ...`); provenance with versions, hash, seed and speed | Low, provided readers look |
| T18 | The simulator profile exhausts host resources | Denial of service | 4 CPU and 4 GB limits on `px4-sim`, 1 CPU and 768 MB on `runner-sim`, single concurrency | Medium on small hosts; the profile is optional and marked experimental |
| T19 | A user scenario overwrites or deletes a library scenario | Tampering | Library scenarios cannot be deleted through the API; creating one with an existing name requires `overwrite: true` | Medium: overwrite is allowed for any name, and without authentication anyone can do it |
| T20 | Prometheus metrics expose sensitive data | Disclosure | Metrics are request counts and latencies by route template and message counters; no identifiers or payloads | Low |

### Assumptions

- The Docker host and the Docker daemon are trusted. The stack does not defend against
  a hostile host.
- The network segment on which port 8080 is published is trusted, or an
  authenticating reverse proxy with TLS is placed in front of the gateway.
- The `.env` file is kept private and its credentials are changed before the
  deployment is shared.
- The mock and replay adapters are code in this repository; the PX4 simulator is an
  upstream image pinned by digest whose own security is outside this model
  (`SECURITY.md` treats upstream issues as out of scope unless this project's default
  configuration makes them exploitable).

### What a vulnerability looks like here

In scope of `SECURITY.md`, and worth a private report:

- any way for a scenario document to execute code, read files outside the scenario
  library or otherwise escape its declarative contract;
- any way for a runner message to move a run into an illegal state or to write outside
  its run's key prefix;
- any stored content that executes in a browser;
- a default configuration of this project that makes an upstream component
  exploitable.

Not in scope: findings that need the default development credentials in a production
deployment, and denial of service of the local simulator through scenario parameters
chosen by an operator of the same deployment.

### Residual risks summarized

Release 0.2.0 is a local, single-tenant tool. Its main residual risks are the absence
of authentication (T10), the reliance on the deployment for TLS and credential hygiene
(T11, T13, T14), and the fact that a runner's own telemetry is trusted for its own run
(T6). None of these is hidden: they are stated in the API description, in
`.env.example`, in the [security model](security-model.md) and in the
[roadmap](roadmap.md). Everything else in the table is addressed by a control that
CI exercises or that a test covers.

# Security model

This document describes the security design of the platform as implemented in
release 0.1.0: what is protected, by which mechanism, and where the mechanism lives in
the code. It is written for people who deploy the platform or review it. The
[threat model](threat-model.md) lists the threats these controls answer and the ones
they do not; `SECURITY.md` at the repository root explains how to report a
vulnerability.

The platform is a defensive engineering tool. It simulates the effects of degradation
on autonomous systems so that engineers can measure recovery. It does not implement,
document or help build any technique for interfering with real aircraft, radios,
navigation receivers or electronics, and contributions in that direction are declined
(`CONTRIBUTING.md`, [em-resilience](em-resilience.md)).

## Principles

1. **Scenarios are data, never code.** The only thing a user can hand the platform is a
   YAML document validated against a closed schema and a closed fault catalog.
2. **Least trust for the component that talks to targets.** Runners execute scenarios
   and drive adapters; they hold no database or object store credentials and every
   message they send is validated before it becomes state.
3. **Validate identifiers at every boundary.** Names that cross a trust boundary
   (scenario names, subsystem ids, run ids, artifact names) match strict patterns
   before they are used in a query, a key or a path.
4. **Minimal, pinned, unprivileged runtime.** Containers run as an unprivileged user
   with a read-only root filesystem, no capabilities, `no-new-privileges`, digest-pinned
   images and internal networks.
5. **Observable, not chatty.** Structured logs with secret redaction, Prometheus
   metrics, and reports that record provenance.

## Scenario documents

The loader (`packages/core/reslab_core/scenario/loader.py`) is the first control on
the main input of the system.

| Control | Implementation |
| ------- | -------------- |
| Size limit | 256 KiB checked on the encoded text before parsing (and on the file size for files); the API also caps `document` fields at 256 KiB |
| Restricted YAML | `yaml.SafeLoader` subclass: no arbitrary object construction, no custom tags |
| Duplicate keys | Rejected by the loader (`duplicate key 'x'`); non-string keys rejected |
| Single document | `load_all` must yield exactly one non-empty document |
| Closed schema | Pydantic models with `extra="forbid"`, frozen, whitespace stripped; unknown keys are errors |
| Closed vocabulary | `target.adapter` is a `Literal`; `effect` is an enum; subsystems must exist in the topology; effects must be allowed for the subsystem by the catalog; parameters must be whitelisted per effect and bounded |
| Bounded collections | At most 128 events, 64 assertions, 8 expectations per event, 8 parameters per injection, 32 configuration entries, 16 labels and tags, 64 waypoints |
| Bounded strings | Names 64, short text 200, long text 4000, expressions 200 characters |
| No paths, no commands | No field of the schema is a path, URL, command or module name. `target.configuration` accepts scalars only (strings at most 200 characters) and adapters must treat them as opaque values |
| Declarative assertions | `path operator literal` grammar parsed by a regular expression; no evaluation of user text; unknown namespaces rejected at load time |
| Durations with units | A bare number is never accepted as a time |

Nothing in the platform ever calls `eval`, `exec`, a shell, or dynamic imports on
scenario content. The same loader is used by the CLI, the API and the runner; a runner
re-validates the canonical YAML it receives in a job (`scenario rejected by runner` if
it somehow fails).

The scenario studio in the browser validates through `POST /api/v1/scenarios/validate`,
so the browser never has its own parser deciding what is valid.

## Identifiers

`packages/core/reslab_core/ids.py` defines the patterns; `validate_run_id`,
`validate_artifact_name` and `validate_slug` are called in the API routers, the
orchestrator and the artifact store.

| Identifier | Pattern | Where enforced |
| ---------- | ------- | -------------- |
| Run id | UUID v4 text form | Every `/api/v1/runs/{run_id}` route (400 on mismatch), the WebSocket route (close code 1008), `artifact_key` |
| Artifact name | `^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,127})$`, additionally no `..`, `/` or `\` | Artifact download route, orchestrator before storing, `artifact_key` |
| Scenario name | Slug pattern, max 64 | Scenario routes |
| Subsystem id | `<category>.<component>`, lowercase snake case | Scenario loader, against the topology |

Artifact keys are always `runs/<validated run id>/<validated name>`; the local store
additionally resolves the path and refuses anything outside its root.

## API

`services/api/reslab_api/app.py` and the routers.

| Control | Implementation |
| ------- | -------------- |
| Body size limit | `BodySizeLimitMiddleware` rejects bodies above `RESLAB_API_MAX_BODY_BYTES` (default 512 KiB) with 413, both from `Content-Length` and by counting streamed bytes |
| CORS | Origins from `RESLAB_API_CORS_ORIGINS` (default `http://localhost:3000,http://localhost:8080`), methods `GET`, `POST`, `DELETE`, `OPTIONS`, headers `Content-Type` and `X-Request-ID`, no credentials |
| Response headers | `X-Request-ID`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` on every response |
| Report CSP | `report.html` and any stored `text/html` artifact are served with `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src data:`; the renderer emits no script, autoescapes template values, and the two inline SVG figures it inserts unescaped are built by the renderer from topology names and numbers, not from user text |
| Downloads | Non-HTML artifacts are served with `Content-Disposition: attachment` and their stored media type |
| Error handling | Scenario validation errors are 422 with structured issues; illegal run transitions 409; invalid identifiers 400; request validation 422; any other exception is logged and answered with a generic 500 (`an internal error occurred`), never a stack trace |
| Pagination caps | Runs list at most 200 per page, events at most 5000, telemetry pages at most `RESLAB_API_TELEMETRY_PAGE_MAX` (default 5000) with a hard cap of 200 000 samples when `all=true` |
| Library protection | Scenarios seeded from `scenarios/` have `source: library` and cannot be deleted through the API |
| Replay source | A replay run must name a `COMPLETED` source run; anything else is rejected |
| Prometheus | `/metrics` is outside the API schema and reachable through the gateway; it exposes request counts and latencies, nothing user-specific |

Interactive documentation is served at `/api/docs` and `/api/redoc`. The OpenAPI
document is committed under `packages/schemas/openapi.json` and CI fails if it drifts
from the code.

### Authentication and authorization

**There is none in this release.** The API description says so: authentication is not
enforced in the local v0.1 deployment, and the API is designed to sit behind an
OIDC-aware gateway. Every request the gateway forwards is trusted. Consequences:

- The reference Compose deployment is meant for a trusted network or a single
  workstation. Do not expose port 8080 to an untrusted network as shipped.
- Adding identity is a gateway concern first (Caddy supports forward authentication
  through plugins or a sidecar) and an API concern second (propagating identity into
  provenance and labels). The [roadmap](roadmap.md) lists this as planned work with no
  code in the repository yet.
- `SECURITY.md` excludes denial of service of the local simulator by an authenticated
  operator of the same deployment from scope; without authentication, "operator" means
  anyone who can reach the gateway.

## Runner protocol and bus

`packages/core/reslab_core/protocol.py`, `packages/platform/reslab_platform/bus/`.

| Control | Implementation |
| ------- | -------------- |
| Typed messages | Every bus payload is a Pydantic model with a `type` discriminator and `protocol_version`; decoding uses a `TypeAdapter` over the union of known messages |
| Payload caps | 8 MiB per message (`MAX_PAYLOAD_BYTES`, mirrored by `max_payload: 8MB` in `infra/nats/nats.conf`); artifact messages carry at most 4 MiB of base64; telemetry batches carry at most 500 samples |
| Undecodable messages | The orchestrator terminates them (`msg.term()`) instead of retrying; the API's core subscription logs and drops them |
| Bounded retries | A message whose handling raised is negatively acknowledged with a 2 s delay and terminated after 5 deliveries |
| Idempotent persistence | Events are unique on `(run_id, sequence)` and telemetry chunks on `(run_id, sequence)`, so redelivery never duplicates data |
| State machine | The orchestrator validates every lifecycle transition against `RUN_TRANSITIONS`; illegal ones are logged and ignored, and terminal runs ignore late messages |
| Runner isolation | Runners connect to NATS only. They receive the scenario in the job, publish results, and have no `RESLAB_DATABASE_URL` or `RESLAB_S3_*` settings in Compose. The replay adapter reads a source run through the API (`RESLAB_API_BASE_URL`), not the database |
| At-most-once jobs | A job is acknowledged on acceptance; a vanished runner is detected by the watchdog, not by redelivery, so a scenario is never silently executed twice |
| Cancellation | Cancel requests travel on core NATS subjects and only affect the named run |

NATS itself runs without authentication inside the internal `control` network in the
reference deployment. `infra/nats/nats.conf` enables JetStream with file storage under
`/data`, a 256 MB memory store and an 8 GB file store limit, and exposes the monitoring
port 8222 (used for health checks and the exporter) inside the internal networks only.

## Storage

| Control | Implementation |
| ------- | -------------- |
| Database access | Only `api`, `orchestrator` and `migrate` receive `RESLAB_DATABASE_URL`; they are on the internal `data` network |
| Migrations | Alembic, applied by the one-shot `migrate` service before the API and orchestrator start (`depends_on: service_completed_successfully`) |
| Object store | S3 API with path-style addressing; keys under `runs/<run_id>/`; SHA-256 recorded per artifact both as object metadata and in the `artifacts` table so a downloaded artifact can be checked against the report |
| Bucket bootstrap | `ensure_ready` creates the bucket when missing and otherwise only checks it exists |
| Credentials | `SecretStr` fields in settings; `repr` masks them; the structured logger redacts keys containing `password`, `secret`, `token`, `authorization`, `access_key`, `secret_key` |

## Containers and Compose

From `compose.yaml`, `infra/docker/python-service.Dockerfile` and
`infra/docker/web.Dockerfile`:

| Control | Implementation |
| ------- | -------------- |
| Unprivileged user | uid and gid 10001 (`reslab`) in both images; CI inspects the built images and fails if `Config.User` is empty or root |
| Read-only root filesystem | `read_only: true` for every Python service and the web app; writable `tmpfs` at `/tmp` (64 MB) and, for the web app, the Next.js cache |
| Capabilities | `cap_drop: [ALL]` on the project's services, the web app, the gateway, NATS and the object store; the gateway adds back only `NET_BIND_SERVICE`. The PostgreSQL, PX4 simulator and observability images keep their image defaults |
| Privilege escalation | `security_opt: no-new-privileges:true` on every service, third-party images included |
| Image pinning | Every `image:` in `compose.yaml` carries a `@sha256:` digest, including PostgreSQL, NATS, RustFS, Caddy, the PX4 simulator image and the observability images; the Dockerfiles pin their base images by digest too; CI rejects an unpinned image |
| No Docker socket, no privileged containers | Enforced by a CI policy check over `compose.yaml` and `infra/` |
| Resource limits | CPU and memory limits on every service except the NATS exporter (for example 512 MB for the Python services, 4 GB for the PX4 simulator) |
| Networks | `edge` (gateway, web, api) is the only bridge with an external route; `control`, `data`, `simulation` and `observability` are `internal: true` |
| Published ports | Only the gateway (`RESLAB_GATEWAY_PORT`, default 8080); Grafana publishes 3001 when the `observability` profile is enabled |
| Health checks | Every long-running service has one; the Python services check `/healthz` (API) or a heartbeat marker file on the private tmpfs (orchestrator, runner) |
| Log rotation | json-file driver capped at 3 files of 10 MB for the Python services |
| Build secrets | A corporate CA bundle can be passed as a BuildKit secret during dependency resolution; it is never stored in a layer |

The gateway (`infra/docker/gateway/Caddyfile`) runs with the admin API off and automatic
HTTPS off, adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and
`Referrer-Policy: no-referrer`, removes the `Server` header, proxies only the API paths
to the API and everything else to the web app, and logs in JSON. TLS termination is
left to the deployment (see [deployment](deployment.md)).

## Provenance and reports

Every run records a `Provenance` object: software, scenario API and protocol versions,
the scenario content hash and version, adapter and adapter version, target
configuration, seed, speed, git commit and image versions when the build provides
them, runner id, non-sensitive environment metadata (Python version, platform,
environment name), start and end times, score profile and `data_origin`. Reports embed
the canonical scenario document that was executed, so a report can always be traced
to exactly what ran. `data_origin` makes it impossible to present mock or replay data
as anything else without editing the report.

## Continuous verification

The `Security` workflow (`.github/workflows/security.yml`) runs on every push and pull
request and weekly:

- dependency review on pull requests (fails on high severity);
- `pip-audit` against the exported lock file and Bandit over the application code;
- `pnpm audit --prod --audit-level high`;
- gitleaks secret scanning over the full history;
- CodeQL for Python and JavaScript/TypeScript with the `security-and-quality` suite;
- a policy check that no Docker socket is mounted, no container is privileged and every
  image is digest-pinned; Trivy configuration scanning of the Dockerfiles; Trivy
  vulnerability scans of the API and web images (high and critical, unfixed ignored)
  uploaded as SARIF; SPDX SBOMs for both images.

The `CI` workflow additionally checks that the published schemas and the generated
TypeScript client match the code, and that the built images do not run as root.

## Known limitations of this release

These are stated here so that nobody deploys with wrong expectations. The
[threat model](threat-model.md) discusses their consequences and the
[roadmap](roadmap.md) tracks them.

- No authentication or authorization on the API or the UI.
- Default development credentials in `.env.example` for PostgreSQL, the object store
  and Grafana; they must be changed for any shared deployment.
- No TLS at the gateway; the deployment must terminate TLS in front of it.
- NATS and PostgreSQL run without authentication or TLS inside the internal networks.
- The RustFS console is enabled in the container (`RUSTFS_CONSOLE_ENABLE`), reachable
  only from the internal `data` network.
- Rate limiting is not implemented; the body size limit and pagination caps bound
  individual requests, not request volume.
- The `security/` directory (`security/policies`, `security/examples`) is reserved for
  policies and example hardening configurations and contains no files in this release.

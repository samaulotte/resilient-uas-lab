# Deployment

The reference deployment is the Docker Compose stack in `compose.yaml`. It runs the
whole platform on one host: the gateway and web application, the three Python
services, a one-shot migration job, and the infrastructure (NATS JetStream, PostgreSQL
17, an S3-compatible object store). Two optional profiles add the PX4 simulator and an
observability stack. This document describes every service, network, volume and
environment variable, the security defaults, and what to change before sharing a
deployment.

The stack has been brought up and exercised end to end in this release (unit,
integration and Playwright suites; see [development](development.md)). The PX4
simulation profile is defined and documented but was not executed as part of that
verification; see [PX4 integration](px4-integration.md).

## Quick reference

```bash
cp .env.example .env
docker compose up --build -d                        # control plane, Mission Control, mock runner
docker compose --profile sim up --build -d          # plus PX4 SITL and the simulation runner (Linux)
docker compose --profile observability up -d        # plus Prometheus, NATS exporter, Grafana
docker compose ps
docker compose logs -f --tail=200
docker compose --profile sim --profile observability down --remove-orphans
```

`make up`, `make sim`, `make observability`, `make down`, `make logs` and `make ps` wrap
the same commands. Mission Control is served at `http://localhost:8080` (or
`RESLAB_GATEWAY_PORT`).

## Services

| Service | Image | Networks | Role |
| ------- | ----- | -------- | ---- |
| `gateway` | `caddy:2.11.4-alpine` (digest pinned) | `edge` | The only published port. Proxies `/api/*`, `/healthz`, `/readyz`, `/metrics` to `api:8000` and everything else to `web:3000`; adds security headers; JSON access log |
| `web` | built from `infra/docker/web.Dockerfile` (Node 22, Next.js standalone) | `edge` | Mission Control |
| `api` | built from `infra/docker/python-service.Dockerfile` with `SERVICE=api` | `edge`, `control`, `data`, `observability` | REST API, WebSocket stream, OpenAPI, probes, Prometheus metrics |
| `orchestrator` | same image, `SERVICE=orchestrator` | `control`, `data`, `observability` | Run state, persistence, watchdog, analysis and reports |
| `runner` | same image, `SERVICE=runner` | `control`, `observability` | Executes runs with the `mock` and `replay` adapters |
| `migrate` | same image, `SERVICE=migrate`, `PACKAGE=reslab-platform` | `data` | One shot: waits for PostgreSQL, applies Alembic migrations, seeds the scenario library, default topology and default score profile; `api` and `orchestrator` start only after it completed successfully |
| `nats` | `nats:2.15.0-alpine` (digest pinned) | `control`, `observability` | JetStream with file storage under `/data`; configuration from `infra/nats/nats.conf` |
| `postgres` | `postgres:17.11` (digest pinned) | `data` | Database |
| `objectstore` | `rustfs/rustfs:1.0.0` (digest pinned) | `data` | S3-compatible artifact store, port 9000 inside the network |
| `px4-sim` (profile `sim`) | `px4io/px4-sitl-gazebo` (digest pinned, overridable with `PX4_SIM_IMAGE`) | `simulation` | PX4 SITL with Gazebo, headless |
| `runner-sim` (profile `sim`) | same Python image, `SERVICE=runner` | `control`, `simulation`, `observability` | Executes runs with the `px4-gazebo` adapter |
| `prometheus` (profile `observability`) | `prom/prometheus:v3.14.0` (digest pinned) | `observability` | Scrapes `api:8000/metrics`, `orchestrator:9101`, `runner:9102`, `nats-exporter:7777`; 7 days retention |
| `nats-exporter` (profile `observability`) | `natsio/prometheus-nats-exporter:0.20.2` (digest pinned) | `observability` | Exposes NATS `varz`, `jsz` and `connz` |
| `grafana` (profile `observability`) | `grafana/grafana:13.2.2` (digest pinned) | `edge`, `observability` | Publishes `RESLAB_GRAFANA_PORT` (default 3001); provisioned Prometheus datasource and the `platform.json` dashboard |

The Python image is multi-stage: dependencies are resolved with `uv sync --frozen
--no-dev` from the lock file in a builder stage and the virtual environment is copied
into a `python:3.12-slim-bookworm` runtime stage together with `scenarios/`, the
entrypoint and the health check script. `RESLAB_SERVICE` selects the process at start
(`api`, `orchestrator`, `runner`, `migrate`, or `cli` to run `reslab`). Images carry
OCI labels with the version and git commit passed as build arguments.

## Networks and ports

| Network | Internal | Members |
| ------- | -------- | ------- |
| `edge` | no | `gateway`, `web`, `api`, `grafana` (observability profile) |
| `control` | yes | `api`, `orchestrator`, `runner`, `runner-sim`, `nats` |
| `data` | yes | `api`, `orchestrator`, `migrate`, `postgres`, `objectstore` |
| `simulation` | yes | `runner-sim`, `px4-sim` |
| `observability` | yes | `api`, `orchestrator`, `runner`, `runner-sim`, `nats`, `prometheus`, `nats-exporter`, `grafana` |

Published ports: `${RESLAB_GATEWAY_PORT:-8080}:80` on the gateway, and
`${RESLAB_GRAFANA_PORT:-3001}:3000` on Grafana when the observability profile is on.
Nothing else is reachable from outside the Docker host. In particular the runners
cannot reach PostgreSQL or the object store, and the simulator is reachable only from
the simulation runner.

## Volumes

| Volume | Service | Contents |
| ------ | ------- | -------- |
| `postgres-data` | `postgres` | Database files |
| `nats-data` | `nats` | JetStream file store (streams `RESLAB_JOBS`, `RESLAB_RUNS`) |
| `objectstore-data` | `objectstore` | Artifacts under `runs/<run_id>/` in bucket `reslab-artifacts` |
| `caddy-data`, `caddy-config` | `gateway` | Caddy state |
| `prometheus-data`, `grafana-data` | observability profile | Time series and Grafana state |

`docker compose down` keeps the volumes; `docker compose down -v` removes them together
with every run. The database is the system of record for runs, events, telemetry
chunks, metrics and assertions; the object store holds the artifacts referenced from
the `artifacts` table. Back up both together. Reports can be regenerated from the
database, artifacts uploaded by adapters cannot.

## Security defaults

The defaults described in the [security model](security-model.md) apply as follows.
The project's own images (`api`, `orchestrator`, `runner`, `runner-sim`, `migrate`,
`web`) run as uid 10001 with a `read_only: true` root filesystem, `tmpfs` at `/tmp`,
`cap_drop: [ALL]` and log rotation. The gateway, NATS and the object store also drop
all capabilities (the gateway adds back `NET_BIND_SERVICE`). Every service, including
PostgreSQL, the simulator and the observability images, sets
`security_opt: no-new-privileges:true`, is pinned by digest and has CPU and memory
limits (the NATS exporter has no explicit limit). Long-running services have health
checks, and no service mounts the Docker socket. The `Security` workflow fails if a
socket mount, a privileged container or an unpinned image appears in `compose.yaml` or
`infra/`.

## Environment variables

Copy `.env.example` to `.env`. Every variable has a working default for a local demo.

### Compose-level variables

| Variable | Default | Used by |
| -------- | ------- | ------- |
| `RESLAB_ENVIRONMENT` | `development` | All Python services (`development`, `test`, `production`) |
| `RESLAB_LOG_LEVEL` | `INFO` | All Python services |
| `RESLAB_LOG_FORMAT` | `json` | All Python services (`json` or `console`) |
| `RESLAB_VERSION` | `0.2.0` | Image build argument, recorded in provenance |
| `RESLAB_GIT_COMMIT` | empty | Image build argument and runtime setting, recorded in provenance |
| `RESLAB_GATEWAY_PORT` | `8080` | Published gateway port |
| `RESLAB_API_CORS_ORIGINS` | `http://localhost:8080,http://localhost:3000` | API |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `reslab`, `reslab`, `reslab` | PostgreSQL and the database URL of `api`, `orchestrator`, `migrate` |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` | `reslab`, `reslab-secret`, `reslab-artifacts` | Object store and the S3 settings of `api`, `orchestrator`, `migrate` |
| `RESLAB_RUNNER_ID` | `runner-1` | `runner` |
| `RESLAB_RUNNER_CONCURRENCY` | `1` | `runner` |
| `RESLAB_RUNNER_STALE_AFTER_SECONDS` | `45` | `orchestrator` |
| `RESLAB_QUEUED_TIMEOUT_SECONDS` | `300` | `orchestrator` |
| `RESLAB_PREPARING_TIMEOUT_SECONDS` | `600` | `orchestrator` |
| `PX4_SIM_IMAGE` | the pinned `px4io/px4-sitl-gazebo` digest | `px4-sim` |
| `PX4_SIM_MODEL` | `gz_x500` | `px4-sim` |
| `PX4_GZ_WORLD` | `default` | `px4-sim` |
| `PX4_SIM_SPEED_FACTOR` | `1` | `px4-sim` |
| `RESLAB_SIM_RUNNER_ID` | `runner-sim-1` | `runner-sim` |
| `RESLAB_PX4_MAVSDK_ADDRESS` | `udpout://px4-sim:14580` | `runner-sim` |
| `RESLAB_PX4_CONNECTION_TIMEOUT_SECONDS` | `120` | `runner-sim` |
| `RESLAB_GRAFANA_PORT` | `3001` | `grafana` |
| `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD` | `admin`, `admin` | `grafana` |

Compose fixes some settings that are not meant to be changed from `.env`:
`RESLAB_NATS_URL=nats://nats:4222`, `RESLAB_SCENARIOS_DIR=/app/scenarios`,
`RESLAB_S3_ENDPOINT_URL=http://objectstore:9000`, `RESLAB_API_PORT=8000`,
`RESLAB_RUNNER_ADAPTERS=mock,replay` on `runner` and `px4-gazebo` on `runner-sim`,
`RESLAB_API_BASE_URL=http://api:8000` on both runners.

### All platform settings

The services read `RESLAB_*` variables through `PlatformSettings`
(`packages/platform/reslab_platform/settings.py`). This is the complete list, useful
when running services outside Compose or on another orchestrator.

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `RESLAB_ENVIRONMENT` | `development` | `development`, `test` or `production`; recorded in provenance |
| `RESLAB_LOG_LEVEL` | `INFO` | Log level |
| `RESLAB_LOG_FORMAT` | `json` | `json` or `console` |
| `RESLAB_DATABASE_URL` | `postgresql+asyncpg://reslab:reslab@localhost:5432/reslab` | SQLAlchemy async URL |
| `RESLAB_DATABASE_POOL_SIZE` | `5` | 1 to 100 |
| `RESLAB_NATS_URL` | `nats://localhost:4222` | Event bus |
| `RESLAB_NATS_STREAM_MAX_AGE_HOURS` | `48` | Retention of both JetStream streams |
| `RESLAB_ARTIFACT_STORE` | `s3` | `s3` or `local` |
| `RESLAB_ARTIFACT_LOCAL_DIR` | `./.reslab/artifacts` | Root of the local store |
| `RESLAB_S3_ENDPOINT_URL` | `http://localhost:9000` | S3 endpoint |
| `RESLAB_S3_REGION` | `us-east-1` | S3 region |
| `RESLAB_S3_BUCKET` | `reslab-artifacts` | Bucket, created if missing |
| `RESLAB_S3_ACCESS_KEY`, `RESLAB_S3_SECRET_KEY` | `reslab`, `reslab-secret` | Credentials (secret values, masked in logs) |
| `RESLAB_S3_FORCE_PATH_STYLE` | `true` | Path-style addressing |
| `RESLAB_SCENARIOS_DIR` | `./scenarios` | Library seeded by `migrate` |
| `RESLAB_API_HOST`, `RESLAB_API_PORT` | `0.0.0.0`, `8000` | API bind address inside the container |
| `RESLAB_API_CORS_ORIGINS` | `http://localhost:3000,http://localhost:8080` | Allowed browser origins |
| `RESLAB_API_MAX_BODY_BYTES` | `524288` | Request body limit (413 above) |
| `RESLAB_API_WS_HEARTBEAT_SECONDS` | `15.0` | WebSocket heartbeat interval |
| `RESLAB_API_TELEMETRY_PAGE_MAX` | `5000` | Maximum samples per telemetry page |
| `RESLAB_ORCHESTRATOR_METRICS_PORT` | `9101` | Prometheus port, 0 disables |
| `RESLAB_ORCHESTRATOR_WATCHDOG_SECONDS` | `10.0` | Watchdog interval |
| `RESLAB_RUNNER_STALE_AFTER_SECONDS` | `45.0` | Seconds without heartbeat or progress before a run is failed |
| `RESLAB_QUEUED_TIMEOUT_SECONDS` | `300.0` | Seconds a queued run waits for a runner |
| `RESLAB_PREPARING_TIMEOUT_SECONDS` | `600.0` | Seconds a run may stay in `PREPARING` before the orchestrator fails it and asks the runner to abort; adapters time out earlier with a precise reason |
| `RESLAB_RUNNER_METRICS_PORT` | `9102` | Prometheus port, 0 disables |
| `RESLAB_RUNNER_ID` | `runner-local` | Runner identity in heartbeats and provenance |
| `RESLAB_RUNNER_ADAPTERS` | `mock,replay` | Adapters this runner offers |
| `RESLAB_RUNNER_HEARTBEAT_SECONDS` | `10.0` | Heartbeat interval |
| `RESLAB_RUNNER_CONCURRENCY` | `1` | Concurrent runs per runner, 1 to 8 |
| `RESLAB_API_BASE_URL` | `http://localhost:8000` | Used by the replay adapter to fetch source runs |
| `RESLAB_GIT_COMMIT` | unset | Recorded in provenance |
| `RESLAB_IMAGE_VERSION` | unset (set by the image) | Recorded in provenance |
| `RESLAB_PX4_MAVSDK_ADDRESS` | `udpin://0.0.0.0:14540` | MAVSDK connection string (Compose overrides to `udpout://px4-sim:14580`) |
| `RESLAB_PX4_CONNECTION_TIMEOUT_SECONDS` | `60.0` | Time to wait for PX4 (Compose sets 120) |

## Health and readiness

| Endpoint or check | Meaning |
| ----------------- | ------- |
| `GET /healthz` (API) | Liveness: the process answers |
| `GET /readyz` (API) | Readiness: `{"status":"ready","components":{"database":true,"bus":true,"artifact_store":true}}`; 503 with `degraded` when the database is unreachable or the state is not built |
| Container health check, API | `python /app/healthcheck.py` requests `/healthz` |
| Container health check, orchestrator and runner | The service touches `/tmp/reslab-<service>-healthy` on its private tmpfs on every loop iteration or heartbeat; the check fails when the marker is older than 90 s |
| `nats` | `http://127.0.0.1:8222/healthz` |
| `postgres` | `pg_isready` |
| `objectstore` | `http://127.0.0.1:9000/health/live` |
| `gateway` | `/healthz` through the proxy |
| `web` | `GET /` on port 3000 |

`docker compose up --wait --wait-timeout 300` returns when every service is healthy;
CI uses exactly that.

## Observability profile

`docker compose --profile observability up -d` starts Prometheus, the NATS exporter and
Grafana. Prometheus scrapes every 15 s: the API's request counter and latency
histogram, the orchestrator's message and finalized-run counters and active-run gauge,
the runner's started, finished and active-run metrics, and NATS server and JetStream
statistics. Grafana is provisioned with the Prometheus datasource and the dashboard in
`infra/observability/grafana/dashboards/platform.json`; log in with
`GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD`, sign-up is disabled and analytics
reporting is off. This is application observability (process health, throughput); the
resilience telemetry of the systems under test is a separate thing and lives in runs.

Logs are structured JSON on stderr from every Python service (`RESLAB_LOG_FORMAT=json`),
with a `service` field and, for API requests, a `request_id` that is also returned in
the `X-Request-ID` header. Secrets are redacted by key name. The gateway logs in JSON
too.

## Simulation profile

`docker compose --profile sim up --build -d` adds `px4-sim` and `runner-sim`. The
simulator image is multi-gigabyte, limited to 4 CPUs and 4 GB, and a Linux host is
recommended. `runner-sim` connects to `px4-sim:14580` over MAVLink and offers the
`px4-gazebo` adapter; it appears in `reslab system` and on the System page once its
first heartbeat arrives. Everything specific to that profile, including its status and
limitations, is in [PX4 integration](px4-integration.md).

## Scaling and variants

- **More runners.** Start additional runner containers with distinct
  `RESLAB_RUNNER_ID` values (for example a second service definition based on `runner`).
  Jobs are distributed through the JetStream work queue; a runner that does not offer
  the requested adapter hands the job back. `RESLAB_RUNNER_CONCURRENCY` runs several
  scenarios in one container; separate containers give better isolation.
- **Another S3 store.** Point `RESLAB_S3_ENDPOINT_URL`, `RESLAB_S3_REGION`,
  `RESLAB_S3_BUCKET` and the credentials at any S3-compatible service and remove or
  disable the `objectstore` service. The client uses path-style addressing by default
  (`RESLAB_S3_FORCE_PATH_STYLE`), standard retries and creates the bucket if it is
  missing.
- **External PostgreSQL or NATS.** Set `RESLAB_DATABASE_URL` and `RESLAB_NATS_URL`
  accordingly; NATS must have JetStream enabled and allow 8 MiB payloads.
- **Running the services without containers.** Each service is a Python module
  (`python -m reslab_api.main`, `reslab_orchestrator.main`, `reslab_runner.main`,
  `reslab_platform.db.cli migrate-and-seed`) configured entirely through `RESLAB_*`
  variables; see [development](development.md).
- **Other orchestrators.** Nothing in the services depends on Compose; preserving the
  network split (runners without storage access, only the gateway published) is the
  one property worth carrying over.

## Before sharing a deployment

The reference stack is a local, single-tenant deployment. Before anyone other than its
operator can reach it:

1. **Change every credential** in `.env`: `POSTGRES_PASSWORD`, `S3_ACCESS_KEY`,
   `S3_SECRET_KEY`, `GRAFANA_ADMIN_PASSWORD`. `SECURITY.md` excludes findings that rely
   on the defaults from its scope because this step is mandatory.
2. **Terminate TLS in front of the gateway.** The bundled Caddy configuration listens
   on plain HTTP on port 80 with automatic HTTPS off, on purpose, so that it can sit
   behind whatever terminates TLS in your environment.
3. **Add authentication at the edge.** The API enforces none in this release (see
   [security model](security-model.md)). Put an authenticating reverse proxy in front
   of port 8080 or restrict the network that can reach it.
4. **Set `RESLAB_ENVIRONMENT=production`** so that provenance records it; set
   `RESLAB_GIT_COMMIT` (CI does this) so reports can be traced to a build.
5. **Review resource limits** for your host, especially if the simulation profile is
   used.
6. **Plan backups** of `postgres-data` and `objectstore-data` together.
7. **Keep images current.** Every image is pinned by digest; Dependabot configuration
   in `.github/dependabot.yml` and the weekly `Security` workflow surface updates and
   advisories, and the CI policy check refuses an unpinned image.

## Upgrading

1. Pull the new revision and rebuild: `docker compose build`.
2. Start the stack; the `migrate` service applies pending Alembic migrations before the
   API and orchestrator start. Migrations live in
   `packages/platform/reslab_platform/db/migrations/versions/`.
3. Check `CHANGELOG.md` for changes to the scenario schema (`apiVersion`), the report
   schema (`schema_version`) or the runner protocol; a protocol change means runners
   and control plane must be upgraded together, which the version field in every
   message makes visible.
4. Runs that were active during the upgrade are failed by the watchdog when their
   runner does not come back; they get an inconclusive report.

## Troubleshooting

| Symptom | Likely cause and check |
| ------- | ---------------------- |
| `api` never becomes healthy | `migrate` did not complete: `docker compose logs migrate`. The database may still be starting or the credentials in `.env` differ from the ones the volume was initialized with |
| `readyz` reports `bus: false` | NATS unhealthy or the API could not connect within 120 s: `docker compose logs nats api` |
| Runs stay `QUEUED`, then fail after 300 s | No online runner offers the adapter; `reslab system` shows adapters and runners. For `px4-gazebo` the `sim` profile must be up |
| Runs fail with `runner ... stopped sending heartbeats` | The runner container restarted or lost the bus; `docker compose logs runner` |
| Report download returns 404 `report not available yet` | The run has not reached `COMPLETED` (or analysis failed: the run's `reason` says `analysis failed: ...`) |
| 413 on scenario upload | Document above 256 KiB or body above `RESLAB_API_MAX_BODY_BYTES` |
| Browser cannot connect the live stream | The stream is at `/api/v1/runs/{id}/stream` on the same origin; a proxy in front of the gateway must pass WebSocket upgrades |
| Corporate TLS interception breaks the image build | Pass the CA bundle as a BuildKit secret: `docker build --secret id=extra_ca,src=/path/to/ca.pem ...` (both Dockerfiles support it; it is never stored in a layer) |

# Development

This document is for people changing the code. It covers the toolchain, how to run the
services outside containers, the test suites and what each one needs, code generation
for schemas and the TypeScript client, the regression check, conventions, and how to
work on a single package. `CONTRIBUTING.md` at the repository root covers process:
issues, branches, pull requests, commit messages and releases.

## Toolchain

| Tool | Version | Notes |
| ---- | ------- | ----- |
| Python | 3.12 | `requires-python = ">=3.12"` in every package |
| uv | `0.8.17` in CI | Workspace manager; `uv.lock` is committed and used with `--frozen` |
| Node.js | 22 (`>=22.12`) | Web application and client |
| pnpm | `10.28.0` | `packageManager` in `package.json`; `pnpm-lock.yaml` committed |
| Docker Engine with Compose v2 | recent | Infrastructure for integration tests, the full stack for end-to-end tests |
| GNU Make | any | Optional; every target is a thin wrapper documented in `make help` |

```bash
make setup        # uv sync --all-packages && pnpm install --frozen-lockfile
```

The Python side is a uv workspace (root `pyproject.toml`) with nine members:
`packages/core`, `packages/platform`, `packages/cli`, `adapters/mock`,
`adapters/px4-gazebo`, `adapters/replay`, `services/api`, `services/orchestrator`,
`services/runner`. Dependencies are pinned exactly in each `pyproject.toml`. The
JavaScript side is a pnpm workspace with `apps/web` and `packages/client`.

## Running the services locally

Start the infrastructure in containers and everything else on the host:

```bash
docker compose up -d postgres nats objectstore
uv run python -m reslab_platform.db.cli migrate-and-seed
```

Then, in separate terminals (`make dev` prints the same list):

```bash
uv run python -m reslab_api.main
uv run python -m reslab_orchestrator.main
uv run python -m reslab_runner.main
NEXT_PUBLIC_API_BASE=http://localhost:8000 pnpm --filter @reslab/web dev
```

The defaults in `PlatformSettings` point at `localhost:5432`, `localhost:4222` and
`localhost:9000` with the development credentials, so no environment variables are
needed for this layout. Useful overrides while developing:

| Variable | Why |
| -------- | --- |
| `RESLAB_LOG_FORMAT=console` | Colored, human-readable logs instead of JSON |
| `RESLAB_LOG_LEVEL=DEBUG` | More detail |
| `RESLAB_ORCHESTRATOR_WATCHDOG_SECONDS=2` | Faster detection of dead runs while testing failure paths |
| `RESLAB_ORCHESTRATOR_METRICS_PORT=0`, `RESLAB_RUNNER_METRICS_PORT=0` | Disable the Prometheus servers when running several instances |
| `RESLAB_RUNNER_ADAPTERS=mock` | Offer fewer adapters |
| `RESLAB_ARTIFACT_STORE=local` | Write artifacts under `./.reslab/artifacts` instead of S3 |

The web application in development mode runs on port 3000 and talks to the API on
port 8000 directly; the API's default CORS origins include both `localhost:3000` and
`localhost:8080` for this reason. In production the web app is served through the
gateway on the same origin and `NEXT_PUBLIC_API_BASE` is empty.

The full list of settings is in [deployment](deployment.md).

## Tests

Unit tests live next to each package (`packages/*/tests`, `adapters/*/tests`,
`services/*/tests`); cross-service suites live under `tests/`. `pytest` is configured
in the root `pyproject.toml` (`asyncio_mode = "auto"`, deprecation warnings from
`reslab_*` modules are errors).

### Unit tests

```bash
make test               # Python and web
make test-python        # uv run pytest -q
make test-web           # pnpm --filter @reslab/web test   (vitest)
```

The Python suite covers the domain model (states and transitions, topology and
propagation depths, the scenario loader's acceptance and rejection rules, the engine
through a fake adapter, metrics, scoring and the report), the platform units, the CLI,
the three adapters (the PX4 adapter through an in-memory fake link), the API, the
orchestrator and the runner. The web suite covers the live-run store, scenario document
helpers, formatting utilities and UI components. In this release the Python suite
reports 137 passed and the web suite 49 passed.

Two `pytest` markers gate the heavier suites: `integration` (needs PostgreSQL, NATS and
an S3 store) and `simulation` (needs a PX4 SITL simulator).

### Integration tests

```bash
docker compose up -d postgres nats objectstore
make test-integration   # RESLAB_INTEGRATION=1 uv run pytest tests/integration -q -m integration
```

The fixture in `tests/integration/conftest.py` migrates and seeds the database, then
spawns the orchestrator, runner (adapters `mock,replay`) and API as subprocesses with
their logs under `artifacts/integration-logs/`, and waits for `/readyz`. The six tests
check that the platform is ready, that the library was seeded, that an invalid
scenario never starts (it is recorded `FAILED` and answered with 422), that the
`compound-degradation` scenario runs end to end through NATS, PostgreSQL and the object
store to a `COMPLETED` run with a report, that replaying that run reproduces its
analysis, and that a running run can be cancelled. The API listens on port 8010 for
these tests (`RESLAB_TEST_API_URL` overrides it).

### End-to-end tests

```bash
docker compose up --build -d --wait
pnpm exec playwright install --with-deps chromium     # once
make e2e                # pnpm exec playwright test -c tests/e2e/playwright.config.ts
```

`tests/e2e/demo-scenario.spec.ts` drives Mission Control through the gateway
(`RESLAB_E2E_BASE_URL`, default `http://localhost:8080`): the application loads and
reports platform status, the demo scenario runs live to completion with a report
(GNSS loss appears in the system panel, the run completes with result `passed`,
`report.json` has schema `1.0`, `report.html` contains `Resilience Report`), the
compare page opens two completed runs, the scenario library and studio validate
documents, and the runs, reports and system pages render. Reports and traces are
written under `tests/e2e/playwright-report/` and `tests/e2e/test-results/`.

### Running the starter scenarios

```bash
make report             # scripts/run_scenarios_local.sh artifacts/reports
```

executes every scenario under `scenarios/` in-process on the mock adapter at 100 times
real time and writes `report.json`, `report.html`, `events.json`, `scenario.yaml` and
the adapter artifacts under `artifacts/reports/<scenario>/<run_id>/`. The script exits
non-zero if any benchmark did not pass.

## Regression check

`reslab regression check` compares candidate `report.json` files against thresholds
and, optionally, a baseline set. Reports are matched by scenario name; a directory is
searched recursively for `report.json` files.

```bash
make regression         # candidate artifacts/reports, baseline artifacts/baseline if present
uv run reslab regression check --candidate artifacts/reports \
    --baseline artifacts/baseline --thresholds regression-thresholds.yaml \
    --json-output artifacts/regression.json
```

Built-in defaults apply when no thresholds file is given, and a thresholds file is
merged over them (top-level keys replace, the `metrics` map is merged per metric):

```yaml
require_passed: true          # the candidate result must be "passed"
score_drop_max: 5.0           # maximum score drop against the baseline, in points
metrics:
  recovery.mttr:
    increase_max: 2.0
  mission.completion:
    decrease_max: 0.05
  containment.flight_domain_affected:
    equals: false
  safety.loss_of_control:
    equals: false
```

Rule types per metric: `equals` (candidate value must equal the literal), `max` and
`min` (absolute limits on the candidate), `increase_max` (candidate minus baseline
must not exceed this; for lower-is-better metrics) and `decrease_max` (baseline minus
candidate must not exceed this; for higher-is-better metrics). Relative rules are
skipped when there is no baseline for the scenario, and the result notes
`no baseline report for this scenario; absolute thresholds only`. The metrics
available to rules are listed in [metrics](metrics.md).

The repository's `regression-thresholds.yaml` adds `recovery.mttr` at most 6 s,
`recovery.success_rate` at least 1.0, `mission.completion` at least 0.80 and
`time.failed` at most 0.0. The check exits with 0 only when every scenario passed;
`--json-output` writes a machine-readable result. Output from this release, with no
baseline:

```
Resilience Regression Check

7 scenarios passed
0 scenarios failed

Scenario: compound-degradation
  Note: no baseline report for this scenario; absolute thresholds only
  Result: PASSED
...
Result: PASSED
```

## Schemas and the TypeScript client

Three generated artifacts are committed and checked in CI:

| Artifact | Generator | Check |
| -------- | --------- | ----- |
| `packages/schemas/scenario.v1alpha1.schema.json`, `report.v1.0.schema.json`, `telemetry-sample.schema.json`, `run-event.schema.json` | `scripts/export_schemas.py` from the Pydantic models | `uv run python scripts/export_schemas.py --check` |
| `packages/schemas/openapi.json` | The same script, from the FastAPI application | same |
| `packages/client/src/schema.d.ts` | `pnpm gen:client` (`openapi-typescript`) from `openapi.json` | `git diff --exit-code` after regenerating |

```bash
make schemas            # RESLAB_LOG_LEVEL=WARNING uv run python scripts/export_schemas.py
make gen-client         # schemas, then pnpm gen:client
```

Run `make gen-client` after any change to a model that is part of the API, the scenario
schema, the report, telemetry or run events, and commit the result. The WebSocket
message models are added to the OpenAPI components explicitly (`x-websocket`) so the
client can type the live stream.

## Linting, formatting, type checking

```bash
make lint               # ruff check, ruff format --check, eslint, prettier --check
make format             # ruff format, ruff check --fix, prettier --write
make typecheck          # tsc --noEmit for client and web
```

Ruff (`pyproject.toml`): line length 100, target Python 3.12, rule sets `E`, `F`, `W`,
`I`, `B`, `UP`, `N`, `S` (Bandit), `ASYNC`, `RUF`, `PTH`, `T20`, with documented
ignores (asserts, pydantic class attributes, framework dependency defaults, binding
`0.0.0.0` inside containers). Tests may use asserts and prints; the CLI may print.
TypeScript is strict with `noUncheckedIndexedAccess`; ESLint runs with
`--max-warnings 0`.

## Conventions

From `CONTRIBUTING.md`, the ones that shape the code:

- State vocabularies live in `reslab_core/states.py` only; UI colors and labels for
  states come from `apps/web/src/lib/states.ts`.
- Pydantic models are `frozen` and `extra="forbid"` unless there is a stated reason.
  Exceptions end in `Error`. Public functions carry type hints.
- No client code fabricates data; anything shown as a value comes from the API or is
  labelled mock or placeholder.
- New runtime dependencies need a sentence in the pull request. Versions are pinned
  exactly.
- Container and Compose changes keep the security defaults; the `Security` workflow
  enforces the ones that can be checked mechanically.
- Every behavioral change gets a test at the lowest level that can observe it.
- Documentation and `CHANGELOG.md` (under *Unreleased*) are updated with the change.
- Conventional Commits; a breaking change to the scenario schema, the API or the report
  format carries `!` and a footer.

## Working on one package

Each workspace member can be exercised alone:

```bash
uv run pytest packages/core/tests -q
uv run pytest adapters/px4-gazebo/tests -q
uv run --package reslab-cli reslab --help
```

`reslab_core` has no I/O dependencies, so domain changes can be developed and tested
without any infrastructure. The engine can be driven directly with a collecting sink,
as `packages/cli/reslab_cli/local.py` does; this is the quickest way to try an adapter
or a metric change end to end. The CLI's `--local` mode is that path packaged for
users.

The web application's tests run with vitest and jsdom (`apps/web/vitest.config.mts`,
setup in `src/test/setup.ts`). Live-run state lives in a zustand store
(`src/stores/live-run.ts`) fed by the WebSocket hook (`src/hooks/use-run-stream.ts`);
data fetching uses TanStack Query through the generated client (`src/lib/api.ts`).

## Continuous integration

`.github/workflows/ci.yml` runs on pushes to `main`, tags `v*`, pull requests and on
demand:

| Job | What it does |
| --- | ------------ |
| `python` | `uv sync --frozen`, Ruff lint and format, unit tests with JUnit output, schema drift check, `reslab scenario validate` on every starter scenario, `scripts/run_scenarios_local.sh`, `reslab regression check` with `regression-thresholds.yaml`; uploads `artifacts/` |
| `web` | `pnpm install --frozen-lockfile`, client regeneration and diff check, Prettier, ESLint, typecheck, vitest, production build |
| `images` | Builds the API and web images with BuildKit cache and fails if either runs as root |
| `integration` | PostgreSQL and RustFS as service containers, NATS started from the repository configuration, then the integration suite |
| `e2e` | `docker compose up --build -d --wait`, waits for `/readyz`, runs Playwright against the gateway, uploads the report, tears down with `-v` |

`.github/workflows/security.yml` is described in the [security model](security-model.md);
`.github/workflows/simulation.yml` (nightly and on demand) in
[PX4 integration](px4-integration.md). Actions are pinned by commit SHA.

## Debugging tips

- Every API response carries `X-Request-ID`; pass your own `X-Request-ID` header to
  correlate a request with the API's JSON logs.
- The event feed is the best first diagnostic for a run: `reslab run --wait` prints
  applied, rejected, observed, recovery, response and mission events as they happen;
  `GET /api/v1/runs/{id}/events?after_sequence=-1&limit=5000` returns them all.
- A run that finished with result `inconclusive` has its `reason` set from the runner
  (`scenario rejected by runner`, `adapter does not support: ...`, `Target failure:
  ...`) or from the watchdog.
- `GET /api/v1/runs/{id}/recording` downloads a run as a replay recording; a run on the
  `replay` adapter with `replay_source_run_id` re-analyzes it without the original
  target.
- `make clean` removes build outputs, caches, local artifacts and Playwright results.

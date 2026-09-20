# Contributing to Resilient UAS Lab

Thank you for considering a contribution. This document explains how the project is
organised, how to set up a development environment, what we expect from changes and how
releases are cut. The technical background lives under `docs/`; start with
`docs/architecture.md` and `docs/development.md`.

## Ground rules

- Be respectful. The [Code of Conduct](CODE_OF_CONDUCT.md) applies to every interaction.
- Stay within scope. The platform simulates the *effects* of degradation on autonomous
  systems. Contributions that implement, describe or parameterise interference,
  spoofing, electromagnetic or any other attack technique are not accepted, however
  well intentioned. `docs/threat-model.md` draws the line precisely.
- Keep scenarios declarative. Scenario documents are data validated against a closed
  schema. Anything that would let a scenario execute code, shell out or load modules is
  rejected in review.
- Report security problems privately, as described in [SECURITY.md](SECURITY.md).

## Development environment

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 22,
[pnpm](https://pnpm.io/) 10, Docker Engine with Compose v2, and GNU Make.

```bash
git clone <your fork>
cd resilient-uas-lab
make setup                       # uv sync --all-packages && pnpm install
docker compose up -d postgres nats objectstore
uv run python -m reslab_platform.db.cli migrate-and-seed
```

Then, in separate terminals, run the three services and the web application in
development mode (`make dev` prints the exact commands). `docs/development.md` covers
environment variables, debugging and how to work on a single package.

The full stack, as users run it, is `docker compose up --build`; Mission Control is
served on http://localhost:8080.

## Repository layout

| Path | Contents |
| ---- | -------- |
| `packages/core` | Domain model: states, scenario schema and loader, fault catalogue, scenario engine, metrics, scoring, reports |
| `packages/platform` | Settings, database models and migrations, event bus client, artifact store |
| `packages/cli` | The `reslab` command line interface |
| `packages/schemas` | Published JSON Schemas and the OpenAPI document (generated, committed) |
| `packages/client` | Generated TypeScript client used by the web application |
| `adapters/` | Target system adapters: `mock`, `px4-gazebo`, `replay` |
| `services/` | `api`, `orchestrator`, `runner` |
| `apps/web` | Mission Control (Next.js) |
| `scenarios/` | Starter scenario library |
| `security/` | Security policies, example hardening configurations |
| `infra/` | Dockerfiles, gateway, NATS and observability configuration |
| `tests/` | Integration and end-to-end suites (unit tests live next to each package) |
| `docs/` | Documentation |

## Making a change

1. Open an issue first for anything larger than a small fix, so that design questions
   are settled before code is written. Scenario proposals and feature requests have
   their own issue forms.
2. Create a branch from `main`.
3. Write the code and the tests. Every behavioural change needs a test at the lowest
   level that can observe it: unit tests in the package, the mock pipeline integration
   suite for cross-service behaviour, Playwright for user-visible flows.
4. Update the documentation and, for user-facing changes, `CHANGELOG.md` under
   *Unreleased*.
5. Run the checks locally:

   ```bash
   make lint          # ruff, eslint, prettier
   make typecheck     # tsc for the client and the web application
   make test          # pytest and vitest
   make gen-client    # regenerates schemas and the TypeScript client; commit the result
   ```

   With infrastructure running (`docker compose up -d postgres nats objectstore`):

   ```bash
   make test-integration
   ```

   With the full stack running (`docker compose up --build -d`):

   ```bash
   make e2e
   ```

6. Open a pull request. The template lists what reviewers look for. CI must be green;
   the `Security` workflow findings are reviewed with the same weight as test failures.

### Coding conventions

- Python: Ruff enforces formatting and linting (`pyproject.toml`). Code is typed;
  public functions carry type hints and docstrings where the name does not already say
  everything. Pydantic models are `frozen` and `extra="forbid"` unless there is a stated
  reason not to be. Exceptions end in `Error`.
- TypeScript: strict mode with `noUncheckedIndexedAccess`. UI components look up colours
  and labels for states in `src/lib/states.ts` rather than hard-coding them. No client
  code fabricates data: anything shown as a value comes from the API or is labelled as
  mock or placeholder in the UI.
- Do not add dependencies casually. A new runtime dependency needs a sentence in the
  pull request explaining why an existing one does not do the job.
- Container and Compose changes keep the security defaults: non-root user, read-only
  root filesystem, dropped capabilities, `no-new-privileges`, images pinned by digest,
  no Docker socket, no privileged containers, internal networks for everything that is
  not the gateway.

### Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(engine): measure recovery from the end of the disturbance window
fix(api): refresh the run after commit before serialising it
docs: describe the recovery time definition
test: add end-to-end demo scenario journey
build(images): update the Python base image digest
```

Types in use: `feat`, `fix`, `docs`, `test`, `build`, `ci`, `refactor`, `perf`,
`chore`. A breaking change to the scenario schema, the API or the report format is
marked with `!` after the type and explained in the footer. Commits are made with the
author's own Git identity; the project does not use trailers.

### Scenario contributions

A new starter scenario is welcome when it tests a behaviour the existing seven do not.
Place the document under `scenarios/`, make sure `uv run reslab scenario validate`
accepts it and `uv run reslab run scenarios/<name>.yaml --local` passes on the mock
adapter, add it to `docs/scenario-format.md`, and (if it should gate releases) to
`regression-thresholds.yaml`. Every expectation and assertion must describe observable
system behaviour in the shared vocabulary of `docs/resilience-model.md`.

### Adapter contributions

`docs/adapter-development.md` describes the contract. An adapter must declare its
capabilities truthfully, reject injections it cannot perform, fail gracefully when the
target is unreachable, and report its `data_origin` so that reports say where the data
came from. Adapters targeting real hardware are outside the scope of this repository.

## Versioning and releases

The project follows semantic versioning. Three things are versioned independently and
documented in `CHANGELOG.md`:

- the software (`reslab_core.versions.SOFTWARE_VERSION`, image labels, CLI `--version`);
- the scenario schema (`apiVersion: resilient-uas.dev/v1alpha1`);
- the report schema (`schema_version` inside `report.json`).

Releases are tagged `vX.Y.Z` on `main` only when the `CI` workflow is green for that
commit. The release notes are the corresponding `CHANGELOG.md` section.

## Licence

By contributing you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE) that covers the project.

# Security Policy

Resilient UAS Lab is a defensive engineering tool. It simulates the *effects* of
degradation on autonomous systems so that engineers can measure how well those systems
recover. The project does not implement, document or help build any technique for
interfering with real aircraft, radios, navigation receivers or electronics. Requests to
add such capabilities are out of scope and will be declined (see `docs/threat-model.md`).

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |

Only the latest minor release receives security fixes. Pre-release builds from `main`
are not supported.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's private vulnerability
reporting: open the **Security** tab of this repository and choose **Report a
vulnerability**. This creates a draft security advisory visible only to the reporter and
the maintainers.

Do not open a public issue, pull request or discussion for a suspected vulnerability.

A useful report contains the affected component (API, orchestrator, runner, adapter,
web application, container image, CI workflow), the version or commit, steps to
reproduce, and the impact you believe it has. Proof-of-concept scenarios or requests are
welcome; working exploits against third-party systems are not needed.

You can expect an acknowledgement within five working days. We will keep you informed
while the report is triaged and fixed, credit you in the advisory if you wish, and
publish the advisory together with the fixed release.

## Scope

In scope:

- The Python services (`services/`), packages (`packages/`) and adapters (`adapters/`).
- The Mission Control web application (`apps/web`).
- The container images, Compose stack and gateway configuration (`infra/`, `compose.yaml`).
- The GitHub Actions workflows (`.github/workflows`).
- The scenario loader and schema: any way for a scenario document to execute code, read
  files outside the scenario library or otherwise escape its declarative contract is a
  vulnerability.

Out of scope:

- Vulnerabilities in upstream projects (PX4, Gazebo, NATS, PostgreSQL, Caddy, RustFS,
  Node.js, Python packages). Please report those upstream; a report here is still
  welcome if the default configuration of this project makes the issue exploitable.
- Findings that require the default development credentials from `.env.example` to be
  used in a production deployment. The deployment guide states that they must be changed.
- Denial of service of the local simulator through scenario parameters chosen by an
  authenticated operator of the same deployment.

## Security design summary

The full model is in `docs/security-model.md` and `docs/threat-model.md`. In short:

- Scenarios are data. They are parsed with a restricted YAML loader, validated against a
  strict schema and a closed fault catalogue, and never evaluated as code.
- Runners are untrusted workers. They receive jobs over the event bus and hold no database
  or object store credentials.
- Every container runs as an unprivileged user with a read-only root filesystem, all
  Linux capabilities dropped and `no-new-privileges` set. No container mounts the Docker
  socket. All images are pinned by digest.
- Stored HTML reports are served with a Content Security Policy that forbids script
  execution.

## Secrets

Never commit `.env` files, private keys, certificates or tokens. The repository ignores
these patterns and CI runs a secret scanner on every push, but the scanner is a safety
net, not a substitute for care. If a secret is committed by mistake, rotate it first and
then contact the maintainers through the channel above so that history can be cleaned.

# Security material

This directory holds the enforceable security policies of the repository and example
hardening configurations for deployments that go beyond the local developer stack.
The narrative behind them is in [`docs/security-model.md`](../docs/security-model.md)
and [`docs/threat-model.md`](../docs/threat-model.md); how to report a vulnerability is
in [`SECURITY.md`](../SECURITY.md).

Nothing in this directory is a secret. It contains no keys, certificates, tokens or
passwords, and the examples reference credentials only through environment variables
that the operator sets outside the repository.

## Layout

| Path | Purpose |
| ---- | ------- |
| `policies/container-hardening.md` | The rules every container image and Compose service must satisfy, and how they are checked |
| `policies/check_compose_policy.sh` | The script that enforces the checkable rules; run locally and in the `Security` workflow |
| `policies/scenario-content.md` | The rules for scenario documents: declarative only, effects only |
| `examples/compose.hardened.yaml` | Compose override for a shared deployment: TLS at the gateway, console disabled, authenticated event bus |
| `examples/Caddyfile.tls` | Gateway configuration with automatic HTTPS for a named host |
| `examples/nats-auth.conf` | NATS server configuration with per-service accounts and least-privilege subject permissions |
| `examples/sros2/` | Example SROS2 access-control policy for the planned ROS 2 adapter |

## Using the examples

The examples are written against the service names and subjects of the reference
`compose.yaml`. They are meant to be copied and adapted, not applied blindly: every
deployment has its own host names, certificate arrangements and secret management.
Each file says what it changes and what the operator must provide.

`examples/sros2/` is provided ahead of the ROS 2 adapter. No code in release 0.2.0
reads it; it documents the access boundary a ROS 2 runner is expected to respect and
gives adapter authors a starting point (see the adapter catalog entry `ros2`, status
`planned`, and [`docs/roadmap.md`](../docs/roadmap.md)).

## Checking the policies locally

```bash
security/policies/check_compose_policy.sh
```

The script exits non-zero and names the offending line when a rule is violated. The
`Security` GitHub Actions workflow runs the same script on every push and pull request.

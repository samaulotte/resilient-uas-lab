# Container hardening policy

This policy applies to every image built from this repository and to every service in
the reference Compose stack, including the `sim` and `observability` profiles. The
rules marked *checked* are enforced by `check_compose_policy.sh`, which runs in the
`Security` workflow and can be run locally; the others are enforced in code review.

## Rules

1. **No Docker socket.** No service mounts `/var/run/docker.sock` or any other path to
   the container runtime, and no configuration file in `infra/` or `security/examples`
   references it. Runners never create containers; the simulator is a separate service
   in the same stack. *Checked.*
2. **No privileged containers.** `privileged: true` is not used anywhere. The only
   capability that may be added is `NET_BIND_SERVICE`, and only on the gateway.
   *Checked.*
3. **Images pinned by digest.** Every pulled image in the Compose file, and every base
   image in the Dockerfiles, is referenced as `name:tag@sha256:...`. Tags are kept for
   readability; digests are what is pulled. Dependabot proposes digest updates.
   *Checked.*
4. **No new privileges.** Every service sets `security_opt: [no-new-privileges:true]`.
   *Checked.*
5. **Project images are minimal at runtime.** Services built from `infra/docker` run
   with `read_only: true`, `cap_drop: [ALL]`, a memory limit, and only tmpfs mounts for
   the paths they must write (`/tmp`, the Next.js cache). *Checked.*
6. **Unprivileged user.** Each Dockerfile ends its runtime stage with `USER` set to a
   dedicated system account (`reslab`, uid 10001). *Checked.*
7. **Least exposure.** Only the gateway publishes a host port (and Grafana, in the
   observability profile, on its own port). Every other network is `internal: true`;
   runners can reach the event bus and the simulator, never the database or the
   object store. *Checked.*
8. **Runners hold no data credentials.** Runner services receive the event bus URL and
   the API base URL only. Database and object store credentials are passed to `api`,
   `orchestrator` and `migrate` and to nothing else.
9. **Multi-stage builds.** Build tooling (uv, pnpm, compilers) stays in build stages;
   runtime images contain the virtual environment or the standalone Next.js output and
   the entrypoint, nothing else. Secrets needed at build time (a corporate CA bundle)
   are passed as BuildKit secrets and never written to a layer.
10. **No secrets in images or the repository.** Credentials come from the environment
    (`.env`, never committed) or from the operator's secret store. `.gitignore` excludes
    `.env*`, keys and certificates; the `Security` workflow scans for leaked secrets.
11. **Health checks without extra tooling.** Python images check health with a small
    script using the standard library; the web image uses Node's `fetch`. No `curl`
    or `wget` is installed in project images.
12. **Reports are inert.** Stored HTML reports and artifacts are served with a Content
    Security Policy of `default-src 'none'; style-src 'unsafe-inline'; img-src data:`,
    which forbids script execution regardless of the stored content.

## Exceptions

An exception must be recorded in this file with the service, the rule, the reason and
the date, and the policy checker must be updated to accept exactly that case.

| Service | Rule | Reason |
| ------- | ---- | ------ |
| `gateway` | 2 | Binds port 80 inside the container as a non-root process; `NET_BIND_SERVICE` is the only added capability |
| `postgres`, `px4-sim`, `prometheus`, `grafana`, `nats-exporter` | 5 | Third-party images that need a writable root filesystem or their own capability set; they keep `no-new-privileges` and digest pinning |
| `migrate` | 5 (memory limit) | One-shot job that exits after applying migrations |

## Verifying a running stack

```bash
docker inspect --format '{{.Name}} user={{.Config.User}} ro={{.HostConfig.ReadonlyRootfs}} caps={{.HostConfig.CapDrop}} secopt={{.HostConfig.SecurityOpt}}' $(docker compose ps -q)
```

Every project container shows `user=reslab:reslab ro=true caps=[ALL]
secopt=[no-new-privileges:true]`.

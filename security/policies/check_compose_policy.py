"""Compose and Dockerfile policy checks (see container-hardening.md).

Reads the resolved Compose configuration as JSON on stdin; the shell wrapper
check_compose_policy.sh produces it with `docker compose config --format json`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

compose_path = sys.argv[1]
config = json.load(sys.stdin)
violations: list[str] = []


def fail(message: str) -> None:
    violations.append(message)


services = config.get("services", {})

# Rule 1: the Docker socket is never mounted.
for name, svc in services.items():
    for volume in svc.get("volumes", []) or []:
        source = volume.get("source", "") if isinstance(volume, dict) else str(volume)
        if "docker.sock" in source:
            fail(f"service '{name}' mounts the Docker socket")

# Rule 2: no privileged containers, no dangerous capabilities added.
for name, svc in services.items():
    if svc.get("privileged"):
        fail(f"service '{name}' is privileged")
    for cap in svc.get("cap_add", []) or []:
        if cap.upper() not in {"NET_BIND_SERVICE"}:
            fail(f"service '{name}' adds capability {cap}")

# Rule 3: every pulled image is pinned by digest (built services are checked via their
# Dockerfile in rule 8).
for name, svc in services.items():
    image = svc.get("image")
    if image and "@sha256:" not in image and "build" not in svc:
        fail(f"service '{name}' image '{image}' is not pinned by digest")

# Rule 4: every service sets no-new-privileges.
for name, svc in services.items():
    opts = svc.get("security_opt", []) or []
    if not any(
        o.replace(" ", "") in {"no-new-privileges:true", "no-new-privileges=true"} for o in opts
    ):
        fail(f"service '{name}' does not set no-new-privileges")

# Rule 5: project images run read-only, drop all capabilities and have resource limits.
for name, svc in services.items():
    if "build" not in svc:
        continue
    if not svc.get("read_only"):
        fail(f"built service '{name}' must set read_only: true")
    if [c.upper() for c in (svc.get("cap_drop") or [])] != ["ALL"]:
        fail(f"built service '{name}' must drop all capabilities")
    limits = ((svc.get("deploy") or {}).get("resources") or {}).get("limits") or {}
    if name != "migrate" and not limits.get("memory"):
        fail(f"built service '{name}' must declare a memory limit")

# Rule 6: only the gateway (and Grafana, in its profile) publish host ports.
for name, svc in services.items():
    if svc.get("ports") and name not in {"gateway", "grafana"}:
        fail(f"service '{name}' publishes a host port; only the gateway (and Grafana) may")

# Rule 7: every network except the browser-facing edge is internal.
for name, net in (config.get("networks") or {}).items():
    if name != "edge" and not net.get("internal"):
        fail(f"network '{name}' must be internal")

# Rule 8: Dockerfiles pin their base images by digest and end as an unprivileged user.
for dockerfile in sorted(Path("infra/docker").glob("*.Dockerfile")):
    text = dockerfile.read_text(encoding="utf-8")
    for match in re.finditer(r"^ARG\s+\w*IMAGE=(\S+)", text, re.MULTILINE):
        if "@sha256:" not in match.group(1):
            fail(f"{dockerfile}: base image '{match.group(1)}' is not pinned by digest")
    for match in re.finditer(r"^FROM\s+(\S+)", text, re.MULTILINE):
        ref = match.group(1)
        if not ref.startswith("${") and "@sha256:" not in ref and ref not in {"deps", "build"}:
            fail(f"{dockerfile}: FROM '{ref}' is not pinned by digest")
    if not re.search(r"^USER\s+[a-z]", text, re.MULTILINE):
        fail(f"{dockerfile}: runtime stage must switch to an unprivileged USER")

# Rule 9: nothing in the repository configuration references the socket or privileged mode.
for path in [Path(compose_path), *Path("infra").rglob("*"), *Path("security/examples").rglob("*")]:
    if (
        path.is_file()
        and path.suffix in {".yaml", ".yml", ".conf", ".Dockerfile", ""}
        and path.stat().st_size < 1_000_000
    ):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "docker.sock" in text:
            fail(f"{path} references the Docker socket")
        if re.search(r"^\s*privileged:\s*true", text, re.MULTILINE):
            fail(f"{path} enables privileged mode")

if violations:
    for v in violations:
        print(f"POLICY VIOLATION: {v}", file=sys.stderr)
    sys.exit(1)
print(f"compose policy: all checks passed ({compose_path}, {len(services)} services)")

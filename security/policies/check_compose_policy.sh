#!/usr/bin/env bash
# Enforce the checkable rules of security/policies/container-hardening.md against the
# Compose stack (all profiles) and the Dockerfiles. Exit non-zero on any violation.
#
#   security/policies/check_compose_policy.sh [compose-file]
#
# Requires Docker Compose v2 (to resolve anchors and profiles) and python3.
set -euo pipefail

cd "$(dirname "$0")/../.."
COMPOSE="${1:-compose.yaml}"

docker compose -f "$COMPOSE" --profile sim --profile observability config --format json \
  | python3 security/policies/check_compose_policy.py "$COMPOSE"


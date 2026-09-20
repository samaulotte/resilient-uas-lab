#!/usr/bin/env bash
# Execute every starter scenario in-process with the mock adapter and write the reports
# under the given directory (default: artifacts/reports). Used by CI and `make report`.
#
#   scripts/run_scenarios_local.sh [output-dir] [speed]
set -euo pipefail

OUT="${1:-artifacts/reports}"
SPEED="${2:-100}"
cd "$(dirname "$0")/.."

mkdir -p "$OUT"
status=0
for scenario in scenarios/*.yaml; do
  name="$(basename "$scenario" .yaml)"
  echo "== $name"
  if ! uv run reslab run "$scenario" --local --speed "$SPEED" -o "$OUT/$name"; then
    echo "   benchmark not passed for $name"
    status=1
  fi
done
echo "reports written under $OUT"
exit $status

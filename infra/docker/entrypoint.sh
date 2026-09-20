#!/bin/sh
# Entrypoint for the Python service image. RESLAB_SERVICE selects the process.
set -eu

case "${RESLAB_SERVICE:-api}" in
  api)          exec python -m reslab_api.main "$@" ;;
  orchestrator) exec python -m reslab_orchestrator.main "$@" ;;
  runner)       exec python -m reslab_runner.main "$@" ;;
  migrate)      exec python -m reslab_platform.db.cli "${@:-migrate-and-seed}" ;;
  cli)          exec reslab "$@" ;;
  *)            echo "unknown RESLAB_SERVICE '${RESLAB_SERVICE}'" >&2; exit 64 ;;
esac

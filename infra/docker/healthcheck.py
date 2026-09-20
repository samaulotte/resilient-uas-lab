"""Container health check for the Python services (no curl in the runtime image).

- api: GET http://localhost:8000/healthz must return 200.
- orchestrator / runner: the heartbeat marker file must be fresh.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request
from pathlib import Path

service = os.environ.get("RESLAB_SERVICE", "api")
try:
    if service == "api":
        port = os.environ.get("RESLAB_API_PORT", "8000")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=3) as response:
            sys.exit(0 if response.status == 200 else 1)
    marker = Path(f"/tmp/reslab-{service}-healthy")  # noqa: S108 - container-local marker
    age = time.time() - marker.stat().st_mtime
    sys.exit(0 if age < 90 else 1)
except Exception:
    sys.exit(1)

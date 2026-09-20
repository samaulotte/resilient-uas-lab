"""Integration test fixtures.

These tests need PostgreSQL, NATS JetStream and an S3-compatible store reachable with
the `RESLAB_*` settings of the environment, and they spawn the orchestrator, runner and
API as subprocesses. They run when `RESLAB_INTEGRATION=1` is set (see `make test-integration`
and `.github/workflows/ci.yml`).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator

import httpx
import pytest
from integration_support import API_URL, REPO_ROOT

pytestmark = pytest.mark.integration


def _integration_enabled() -> bool:
    return os.environ.get("RESLAB_INTEGRATION") == "1"


@pytest.fixture(scope="session")
def platform() -> Iterator[str]:
    if not _integration_enabled():
        pytest.skip("set RESLAB_INTEGRATION=1 to run integration tests")
    env = dict(os.environ)
    env.setdefault("RESLAB_LOG_FORMAT", "json")
    env.setdefault("RESLAB_LOG_LEVEL", "INFO")
    env.setdefault("RESLAB_SCENARIOS_DIR", str(REPO_ROOT / "scenarios"))
    env["RESLAB_API_PORT"] = API_URL.rsplit(":", 1)[1]
    env["RESLAB_API_BASE_URL"] = API_URL
    env.setdefault("RESLAB_RUNNER_ID", "runner-integration")
    env.setdefault("RESLAB_RUNNER_ADAPTERS", "mock,replay")
    env["RESLAB_ORCHESTRATOR_WATCHDOG_SECONDS"] = "2"
    env["RESLAB_ORCHESTRATOR_METRICS_PORT"] = "0"
    env["RESLAB_RUNNER_METRICS_PORT"] = "0"

    subprocess.run(
        [sys.executable, "-m", "reslab_platform.db.cli", "migrate-and-seed"],
        check=True,
        env=env,
        cwd=REPO_ROOT,
        timeout=180,
    )
    log_dir = REPO_ROOT / "artifacts" / "integration-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    processes: list[subprocess.Popen[bytes]] = []
    for module in ("reslab_orchestrator.main", "reslab_runner.main", "reslab_api.main"):
        log_file = (log_dir / f"{module.split('.')[0]}.log").open("wb")
        processes.append(
            subprocess.Popen(
                [sys.executable, "-m", module],
                env=env,
                cwd=REPO_ROOT,
                stdout=log_file,
                stderr=log_file,
            )
        )
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                response = httpx.get(f"{API_URL}/readyz", timeout=2)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if any(p.poll() is not None for p in processes):
                raise RuntimeError(
                    "a platform process exited during startup; see artifacts/integration-logs"
                )
            time.sleep(1)
        else:
            raise RuntimeError("API did not become ready")
        # Wait for the runner to announce itself.
        deadline = time.time() + 60
        while time.time() < deadline:
            info = httpx.get(f"{API_URL}/api/v1/system", timeout=10).json()
            if any(r["online"] for r in info["runners"]):
                break
            time.sleep(1)
        yield API_URL
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()


@pytest.fixture
def client(platform: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=platform, timeout=60) as http:
        yield http

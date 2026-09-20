"""Shared constants and helpers for the integration tests."""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
API_URL = os.environ.get("RESLAB_TEST_API_URL", "http://127.0.0.1:8010")


def wait_for_terminal(client: httpx.Client, run_id: str, timeout: float = 240) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = client.get(f"/api/v1/runs/{run_id}").json()
        if run["state"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return run
        time.sleep(1)
    raise AssertionError(f"run {run_id} did not finish in {timeout}s")

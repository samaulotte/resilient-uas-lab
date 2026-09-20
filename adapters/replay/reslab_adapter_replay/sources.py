from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from reslab_core.telemetry import PlannedPath, RunEvent, TelemetrySample


class ReplayRecording(BaseModel):
    """Everything the replay adapter needs. Producers: API export, future ULog/rosbag converters."""

    model_config = ConfigDict(frozen=True)

    format_version: str = "1"
    source_run_id: str | None = None
    source_adapter: str = "unknown"
    scenario_name: str = ""
    planned_path: PlannedPath | None = None
    samples: list[TelemetrySample] = Field(min_length=1)
    events: list[RunEvent] = Field(default_factory=list)


class ReplaySource(Protocol):
    async def load(self) -> ReplayRecording: ...

    def describe(self) -> str: ...


class FileReplaySource:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def load(self) -> ReplayRecording:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return ReplayRecording.model_validate(data)

    def describe(self) -> str:
        return f"file:{self.path.name}"


class ApiReplaySource:
    """Loads a completed run from the platform API."""

    def __init__(self, base_url: str, run_id: str, *, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.run_id = run_id
        self.timeout = timeout

    async def load(self) -> ReplayRecording:
        import httpx

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            run = (await client.get(f"/api/v1/runs/{self.run_id}")).raise_for_status().json()
            telemetry = (
                (await client.get(f"/api/v1/runs/{self.run_id}/telemetry", params={"all": "true"}))
                .raise_for_status()
                .json()
            )
            events = (
                (await client.get(f"/api/v1/runs/{self.run_id}/events", params={"limit": 5000}))
                .raise_for_status()
                .json()
            )
        return ReplayRecording(
            source_run_id=self.run_id,
            source_adapter=str(run.get("adapter", "unknown")),
            scenario_name=str(run.get("scenario_name", "")),
            planned_path=(
                PlannedPath.model_validate(run["planned_path"]) if run.get("planned_path") else None
            ),
            samples=[TelemetrySample.model_validate(s) for s in telemetry.get("samples", [])],
            events=[RunEvent.model_validate(e) for e in events.get("events", [])],
        )

    def describe(self) -> str:
        return f"api:{self.run_id}"

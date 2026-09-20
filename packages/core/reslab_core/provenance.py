"""Run provenance: everything needed to reproduce or audit a run."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from reslab_core.versions import PROTOCOL_VERSION, SCENARIO_API_VERSION, SOFTWARE_VERSION


class Provenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    software_version: str = SOFTWARE_VERSION
    scenario_api_version: str = SCENARIO_API_VERSION
    protocol_version: str = PROTOCOL_VERSION
    scenario_hash: str = Field(description="sha256 of the canonical scenario document")
    scenario_version: str
    adapter: str
    adapter_version: str | None = None
    target_configuration: dict[str, str | int | float | bool] = Field(default_factory=dict)
    seed: int
    speed: float
    git_commit: str | None = Field(default=None, description="Git SHA of the platform build")
    image_versions: dict[str, str] = Field(default_factory=dict)
    runner_id: str | None = None
    environment: dict[str, str] = Field(
        default_factory=dict, description="Non-sensitive environment metadata (platform, python)"
    )
    started_at: datetime | None = None
    ended_at: datetime | None = None
    score_profile: str = "default"
    data_origin: str = Field(
        default="simulation", description="simulation, replay or hardware-in-the-loop"
    )

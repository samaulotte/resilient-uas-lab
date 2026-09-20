"""Platform settings, read from the environment (see `.env.example`).

Secrets are never logged; `repr` of the settings object masks them.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PlatformSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RESLAB_", env_file=None, extra="ignore", case_sensitive=False
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://reslab:reslab@localhost:5432/reslab",
        description="SQLAlchemy async URL (postgresql+asyncpg://...)",
    )
    database_pool_size: int = Field(default=5, ge=1, le=100)

    # Event bus
    nats_url: str = "nats://localhost:4222"
    nats_stream_max_age_hours: int = Field(default=48, ge=1)

    # Artifact storage
    artifact_store: Literal["s3", "local"] = "s3"
    artifact_local_dir: Path = Path("./.reslab/artifacts")
    s3_endpoint_url: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "reslab-artifacts"
    s3_access_key: SecretStr = SecretStr("reslab")
    s3_secret_key: SecretStr = SecretStr("reslab-secret")
    s3_force_path_style: bool = True

    # Scenario library
    scenarios_dir: Path = Path("./scenarios")

    # API
    # Bound inside the container; the gateway is the only published endpoint.
    api_host: str = "0.0.0.0"  # nosec B104
    api_port: int = 8000
    api_cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8080",
        description="Comma separated list of allowed browser origins",
    )
    api_max_body_bytes: int = Field(default=512 * 1024, ge=1024)
    api_ws_heartbeat_seconds: float = Field(default=15.0, gt=0)
    api_telemetry_page_max: int = Field(default=5000, ge=100)

    # Orchestrator
    orchestrator_metrics_port: int = Field(
        default=9101, ge=0, le=65535, description="Prometheus port, 0 disables"
    )
    orchestrator_watchdog_seconds: float = Field(default=10.0, gt=0)
    runner_stale_after_seconds: float = Field(default=45.0, gt=0)
    queued_timeout_seconds: float = Field(default=300.0, gt=0)
    # A run may stay in PREPARING (adapter connecting to its target) at most this long.
    # Keep it above the adapters' own connection timeouts so they fail first with a
    # precise reason; this is the orchestrator's backstop.
    preparing_timeout_seconds: float = Field(default=600.0, gt=0)

    # Runner
    runner_metrics_port: int = Field(
        default=9102, ge=0, le=65535, description="Prometheus port, 0 disables"
    )
    runner_id: str = Field(default="runner-local")
    runner_adapters: str = Field(
        default="mock,replay", description="Comma separated adapters this runner offers"
    )
    runner_heartbeat_seconds: float = Field(default=10.0, gt=0)
    runner_concurrency: int = Field(default=1, ge=1, le=8)
    api_base_url: str = Field(
        default="http://localhost:8000", description="Used by the replay adapter to fetch runs"
    )

    # Provenance
    git_commit: str | None = Field(default=None, description="Git SHA of the running build")
    image_version: str | None = Field(default=None, description="Container image tag")

    # Simulation (PX4)
    px4_mavsdk_address: str = Field(default="udpin://0.0.0.0:14550")
    px4_connection_timeout_seconds: float = Field(default=60.0, gt=0)

    @field_validator("log_level")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def runner_adapter_list(self) -> list[str]:
        return [a.strip() for a in self.runner_adapters.split(",") if a.strip()]

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "+psycopg").replace("+psycopg", "")


@lru_cache(maxsize=1)
def get_settings() -> PlatformSettings:
    return PlatformSettings()

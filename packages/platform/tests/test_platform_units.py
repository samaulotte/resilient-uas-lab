from __future__ import annotations

import pytest

from reslab_core.protocol import RunJob, RunnerHeartbeat, TelemetryMessage
from reslab_platform.artifacts import LocalArtifactStore, artifact_key
from reslab_platform.bus import Subjects, decode_message, encode_message
from reslab_platform.settings import PlatformSettings

RUN_ID = "00000000-0000-4000-8000-000000000009"


def test_settings_defaults_and_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESLAB_RUNNER_ADAPTERS", "mock, px4-gazebo")
    monkeypatch.setenv("RESLAB_API_CORS_ORIGINS", "http://a:1,http://b:2")
    monkeypatch.setenv("RESLAB_LOG_LEVEL", "debug")
    settings = PlatformSettings()
    assert settings.runner_adapter_list == ["mock", "px4-gazebo"]
    assert settings.cors_origins == ["http://a:1", "http://b:2"]
    assert settings.log_level == "DEBUG"
    assert "reslab-secret" not in repr(settings)


def test_artifact_key_rejects_traversal() -> None:
    assert artifact_key(RUN_ID, "report.json") == f"runs/{RUN_ID}/report.json"
    with pytest.raises(ValueError, match="invalid artifact name"):
        artifact_key(RUN_ID, "../secrets")
    with pytest.raises(ValueError, match="invalid run id"):
        artifact_key("not-a-run", "report.json")


async def test_local_store_round_trip(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    await store.ensure_ready()
    stored = await store.put(RUN_ID, "report.json", b'{"ok": true}', "application/json")
    assert stored.size_bytes == 12
    assert stored.sha256
    assert await store.exists(RUN_ID, "report.json")
    assert await store.get(RUN_ID, "report.json") == b'{"ok": true}'
    assert await store.list(RUN_ID) == ["report.json"]
    assert not await store.exists(RUN_ID, "missing.json")
    assert store.describe().startswith("local:")


def test_protocol_codec_dispatches_on_type() -> None:
    job = RunJob(
        run_id=RUN_ID,
        scenario_yaml="x",
        scenario_hash="sha256:1",
        adapter="mock",
        seed=1,
        speed=1.0,
    )
    decoded = decode_message(encode_message(job))
    assert isinstance(decoded, RunJob)
    assert decoded.run_id == RUN_ID
    heartbeat = decode_message(
        encode_message(RunnerHeartbeat(runner_id="r1", adapters=["mock"], version="0.1.0"))
    )
    assert isinstance(heartbeat, RunnerHeartbeat)
    with pytest.raises(ValueError, match="payload limit"):
        decode_message(b"x" * (8 * 1024 * 1024 + 1))


def test_telemetry_message_requires_samples() -> None:
    with pytest.raises(ValueError):
        TelemetryMessage(run_id=RUN_ID, sequence=0, samples=[])


def test_subjects() -> None:
    assert Subjects.run_telemetry(RUN_ID) == f"reslab.runs.{RUN_ID}.telemetry"
    assert Subjects.run_id_from_subject(Subjects.run_events(RUN_ID)) == RUN_ID
    assert Subjects.run_id_from_subject(Subjects.control_cancel(RUN_ID)) == RUN_ID
    assert Subjects.run_id_from_subject("reslab.runners.heartbeat") is None

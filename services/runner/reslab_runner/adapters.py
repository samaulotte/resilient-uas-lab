"""Adapter registry for the runner.

Adapters are constructed by name. Heavy adapters (PX4 needs MAVSDK) are imported lazily
so a runner offering only the mock adapter never loads simulator dependencies.
"""

from __future__ import annotations

from collections.abc import Callable

from reslab_core.adapter import AdapterCapabilities, AutonomousSystemAdapter
from reslab_core.protocol import RunJob
from reslab_platform.settings import PlatformSettings

AdapterFactory = Callable[[RunJob, PlatformSettings], AutonomousSystemAdapter]


def _mock(job: RunJob, settings: PlatformSettings) -> AutonomousSystemAdapter:
    from reslab_adapter_mock import MockAdapter

    return MockAdapter()


def _replay(job: RunJob, settings: PlatformSettings) -> AutonomousSystemAdapter:
    from reslab_adapter_replay import ApiReplaySource, ReplayAdapter

    if not job.replay_source_run_id:
        raise ValueError("replay adapter requires replay_source_run_id")
    return ReplayAdapter(ApiReplaySource(settings.api_base_url, job.replay_source_run_id))


def _px4(job: RunJob, settings: PlatformSettings) -> AutonomousSystemAdapter:
    from reslab_adapter_px4 import PX4GazeboAdapter

    return PX4GazeboAdapter(
        connection_url=settings.px4_mavsdk_address,
        connection_timeout=settings.px4_connection_timeout_seconds,
    )


FACTORIES: dict[str, AdapterFactory] = {
    "mock": _mock,
    "replay": _replay,
    "px4-gazebo": _px4,
}


def capabilities_for(name: str) -> AdapterCapabilities | None:
    if name == "mock":
        from reslab_adapter_mock import MOCK_CAPABILITIES

        return MOCK_CAPABILITIES
    if name == "replay":
        from reslab_adapter_replay import REPLAY_CAPABILITIES

        return REPLAY_CAPABILITIES
    if name == "px4-gazebo":
        from reslab_adapter_px4 import PX4_CAPABILITIES

        return PX4_CAPABILITIES
    return None


def create_adapter(job: RunJob, settings: PlatformSettings) -> AutonomousSystemAdapter:
    factory = FACTORIES.get(job.adapter)
    if factory is None:
        raise ValueError(f"unknown adapter '{job.adapter}'")
    return factory(job, settings)

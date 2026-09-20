"""Replay adapter: re-emits normalized telemetry and events of a recorded run.

Sources are pluggable (`ReplaySource`). v0.1 ships an API source (a completed run of
this platform) and a file source (JSON recording). Future sources such as PX4 ULog or
rosbag only need to produce a `ReplayRecording`.
"""

from reslab_adapter_replay.adapter import REPLAY_CAPABILITIES, ReplayAdapter
from reslab_adapter_replay.sources import (
    ApiReplaySource,
    FileReplaySource,
    ReplayRecording,
    ReplaySource,
)

__all__ = [
    "REPLAY_CAPABILITIES",
    "ApiReplaySource",
    "FileReplaySource",
    "ReplayAdapter",
    "ReplayRecording",
    "ReplaySource",
]

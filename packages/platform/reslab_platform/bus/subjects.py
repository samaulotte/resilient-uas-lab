"""Subject and stream naming.

Streams:

- `RESLAB_JOBS` (work queue): `reslab.jobs.run` consumed by the runner pool.
- `RESLAB_RUNS` (limits, bounded retention): everything runners publish about a run.

Core (non-persisted) subjects: control messages and runner heartbeats.
"""

from __future__ import annotations

JOBS_STREAM = "RESLAB_JOBS"
RUNS_STREAM = "RESLAB_RUNS"

JOBS_CONSUMER = "runners"
ORCHESTRATOR_CONSUMER = "orchestrator"


class Subjects:
    JOBS_RUN = "reslab.jobs.run"
    JOBS_WILDCARD = "reslab.jobs.>"
    RUNS_WILDCARD = "reslab.runs.>"
    RUNNER_HEARTBEAT = "reslab.runners.heartbeat"
    CONTROL_WILDCARD = "reslab.control.>"

    @staticmethod
    def run_lifecycle(run_id: str) -> str:
        return f"reslab.runs.{run_id}.lifecycle"

    @staticmethod
    def run_events(run_id: str) -> str:
        return f"reslab.runs.{run_id}.events"

    @staticmethod
    def run_telemetry(run_id: str) -> str:
        return f"reslab.runs.{run_id}.telemetry"

    @staticmethod
    def run_artifacts(run_id: str) -> str:
        return f"reslab.runs.{run_id}.artifacts"

    @staticmethod
    def run_finished(run_id: str) -> str:
        return f"reslab.runs.{run_id}.finished"

    @staticmethod
    def run_wildcard(run_id: str) -> str:
        return f"reslab.runs.{run_id}.>"

    @staticmethod
    def control_cancel(run_id: str) -> str:
        return f"reslab.control.{run_id}.cancel"

    @staticmethod
    def run_id_from_subject(subject: str) -> str | None:
        parts = subject.split(".")
        if len(parts) >= 4 and parts[0] == "reslab" and parts[1] in ("runs", "control"):
            return parts[2]
        return None

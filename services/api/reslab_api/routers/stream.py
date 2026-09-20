"""Live run stream over WebSocket.

Protocol (server -> client), JSON text frames:

- `snapshot`: run detail, recent events and a telemetry tail, sent once on connect;
- `lifecycle`, `event`, `telemetry`, `run_finished`: runner messages relayed live;
- `heartbeat`: sent every `api_ws_heartbeat_seconds` when nothing else flows;
- `completed`: final run summary once the orchestrator finalized the run, then close.

Client -> server frames are ignored except `{"type":"ping"}` which is answered with
a heartbeat. Reconnecting clients get a fresh snapshot, so nothing is lost when a
run completes while the browser was disconnected.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from reslab_api.schemas import StreamCompleted, StreamHeartbeat, StreamSnapshot
from reslab_api.services.runs import run_detail, run_summary
from reslab_api.state import get_ws_state
from reslab_core.ids import InvalidIdentifierError, validate_run_id
from reslab_core.states import RunState
from reslab_platform.db import repository
from reslab_platform.logging import get_logger

router = APIRouter(tags=["stream"])
log = get_logger(__name__)

SNAPSHOT_EVENTS = 300
SNAPSHOT_TELEMETRY = 600


@router.websocket("/api/v1/runs/{run_id}/stream")
async def stream(websocket: WebSocket, run_id: str) -> None:
    state = get_ws_state(websocket)
    try:
        validate_run_id(run_id)
    except InvalidIdentifierError:
        await websocket.close(code=1008, reason="invalid run id")
        return

    async with state.sessions() as session:
        run = await repository.get_run(session, run_id)
        if run is None:
            await websocket.close(code=1008, reason="run not found")
            return
        detail = await run_detail(session, run)
        events = await repository.list_events(session, run_id, limit=100_000)
        events = events[-SNAPSHOT_EVENTS:]
        total, _ = await repository.telemetry_stats(session, run_id)
        stride = max(1, -(-total // SNAPSHOT_TELEMETRY))
        telemetry = await repository.list_telemetry(session, run_id, stride=stride)

    await websocket.accept()
    queue = state.hub.subscribe(run_id)
    heartbeat = state.settings.api_ws_heartbeat_seconds
    try:
        await websocket.send_text(
            StreamSnapshot(
                run=detail, events=events, telemetry=telemetry, server_time=datetime.now(tz=UTC)
            ).model_dump_json()
        )
        if RunState(detail.state).is_terminal:
            await websocket.send_text(
                StreamCompleted(
                    run=run_summary(run), report_available=detail.report_available
                ).model_dump_json()
            )
            await websocket.close(code=1000)
            return

        reader = asyncio.create_task(_drain_client(websocket), name=f"ws-reader-{run_id}")
        finished_seen = False
        try:
            while True:
                if reader.done():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                except TimeoutError:
                    if finished_seen:
                        completed = await _completed_if_terminal(state, run_id)
                        if completed is not None:
                            await websocket.send_text(completed.model_dump_json())
                            await websocket.close(code=1000)
                            return
                    await websocket.send_text(
                        StreamHeartbeat(server_time=datetime.now(tz=UTC)).model_dump_json()
                    )
                    continue
                await websocket.send_text(message.model_dump_json())
                if message.type == "run_finished":
                    finished_seen = True
                    completed = await _wait_for_terminal(state, run_id)
                    if completed is not None:
                        await websocket.send_text(completed.model_dump_json())
                        await websocket.close(code=1000)
                        return
        finally:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await reader
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("ws.stream_error", run_id=run_id, error=str(exc))
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason="stream error")
    finally:
        state.hub.unsubscribe(run_id, queue)


async def _drain_client(websocket: WebSocket) -> None:
    while True:
        text = await websocket.receive_text()
        if text.strip() == '{"type":"ping"}':
            await websocket.send_text(
                StreamHeartbeat(server_time=datetime.now(tz=UTC)).model_dump_json()
            )


async def _completed_if_terminal(state, run_id: str) -> StreamCompleted | None:
    async with state.sessions() as session:
        run = await repository.get_run(session, run_id)
        if run is None or not RunState(run.state).is_terminal:
            return None
        artifacts = await repository.list_artifacts(session, run_id)
        return StreamCompleted(
            run=run_summary(run),
            report_available=any(a.name == "report.json" for a in artifacts),
        )


async def _wait_for_terminal(state, run_id: str, timeout: float = 120.0) -> StreamCompleted | None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        completed = await _completed_if_terminal(state, run_id)
        if completed is not None:
            return completed
        await asyncio.sleep(0.5)
    return None

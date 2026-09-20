from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from reslab_api.app import BodySizeLimitMiddleware
from reslab_api.services.compare import METRIC_DEFINITIONS, MetricDefinition, _verdict


def _definition(key: str) -> MetricDefinition:
    return next(d for d in METRIC_DEFINITIONS if d.key == key)


def test_higher_is_better_semantics() -> None:
    completion = _definition("mission.completion")
    assert _verdict(completion, 0.90, 0.95)[1] == "improvement"
    assert _verdict(completion, 0.95, 0.90)[1] == "regression"
    assert _verdict(completion, 0.950, 0.951)[1] == "unchanged"


def test_lower_is_better_semantics() -> None:
    mttr = _definition("recovery.mttr")
    delta, verdict = _verdict(mttr, 4.1, 9.8)
    assert verdict == "regression" and delta == pytest.approx(5.7)
    assert _verdict(mttr, 9.8, 4.1)[1] == "improvement"


def test_neutral_metrics_are_never_called_improvements() -> None:
    injected = _definition("events.injected")
    assert _verdict(injected, 3, 4)[1] == "changed"
    assert _verdict(injected, 3, 3)[1] == "unchanged"


def test_boolean_and_missing_values() -> None:
    contained = _definition("containment.contained")
    assert _verdict(contained, False, True)[1] == "improvement"
    assert _verdict(contained, True, False)[1] == "regression"
    loss = _definition("safety.loss_of_control")
    assert _verdict(loss, False, True)[1] == "regression"
    assert _verdict(loss, None, True)[1] == "not_comparable"


async def test_body_size_limit_middleware() -> None:
    app = FastAPI()

    @app.post("/echo")
    async def echo(payload: dict) -> dict:
        return payload

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=64)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.post("/echo", json={"a": 1})
        assert ok.status_code == 200
        too_large = await client.post("/echo", json={"a": "x" * 200})
        assert too_large.status_code == 413
        assert too_large.json()["error"] == "payload_too_large"

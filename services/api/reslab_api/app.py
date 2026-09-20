"""FastAPI application factory."""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from reslab_api.routers import compare, health, runs, scenarios, stream, system
from reslab_api.state import build_state, start_state, stop_state
from reslab_core.ids import InvalidIdentifierError
from reslab_core.scenario import ScenarioValidationError
from reslab_core.states import InvalidRunTransitionError
from reslab_core.versions import SOFTWARE_VERSION
from reslab_platform.logging import configure_logging, get_logger
from reslab_platform.settings import PlatformSettings, get_settings

log = get_logger(__name__)

REQUESTS = Counter("reslab_api_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("reslab_api_request_seconds", "HTTP request latency", ["method", "path"])

API_DESCRIPTION = """
Resilient UAS Lab control-plane API.

Resilience scenarios are declarative YAML documents validated against a versioned
schema. Runs execute scenarios against an autonomous-system adapter and produce
normalized telemetry, classified events, objective metrics, a transparent score and a
canonical report. Live run state is streamed over `WS /api/v1/runs/{run_id}/stream`.

Authentication is not enforced in the local v0.1 deployment; the API is designed to
sit behind an OIDC-aware gateway (see docs/security-model.md).
"""


class BodySizeLimitMiddleware:
    """Reject request bodies larger than the configured limit (413)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        declared = headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            response = JSONResponse(
                {"error": "payload_too_large", "detail": "request body too large"}, 413
            )
            await response(scope, receive, send)
            return
        received = 0
        rejected = False

        async def limited_receive() -> Message:
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes and not rejected:
                    rejected = True
                    raise PayloadTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except PayloadTooLargeError:
            response = JSONResponse(
                {"error": "payload_too_large", "detail": "request body too large"}, 413
            )
            await response(scope, receive, send)


class PayloadTooLargeError(Exception):
    pass


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        structlog.contextvars.bind_contextvars(request_id=request_id)
        route = request.scope.get("route")
        path_template = getattr(route, "path", request.url.path)
        with LATENCY.labels(request.method, path_template).time():
            response = await call_next(request)
        REQUESTS.labels(request.method, path_template, str(response.status_code)).inc()
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        structlog.contextvars.unbind_contextvars("request_id")
        return response


def create_app(settings: PlatformSettings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format, service="api")

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = await build_state(settings)
        app.state.reslab = state
        await start_state(state)
        log.info("api.started", version=SOFTWARE_VERSION, environment=settings.environment)
        try:
            yield
        finally:
            await stop_state(state)
            log.info("api.stopped")

    app = FastAPI(
        title="Resilient UAS Lab API",
        version=SOFTWARE_VERSION,
        description=API_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        openapi_tags=[
            {
                "name": "system",
                "description": "Platform, topology, fault catalog, adapters, runners",
            },
            {"name": "scenarios", "description": "Scenario library and validation"},
            {"name": "runs", "description": "Run lifecycle, events, telemetry, metrics, reports"},
            {"name": "compare", "description": "Two-run comparison"},
            {"name": "stream", "description": "Live run stream (WebSocket)"},
            {"name": "health", "description": "Probes"},
        ],
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.api_max_body_bytes)

    app.include_router(health.router)
    app.include_router(system.router)
    app.include_router(scenarios.router)
    app.include_router(runs.router)
    app.include_router(compare.router)
    app.include_router(stream.router)

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.exception_handler(ScenarioValidationError)
    async def _scenario_error(_: Request, exc: ScenarioValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_scenario",
                "detail": str(exc),
                "issues": [i.model_dump() for i in exc.issues],
            },
        )

    @app.exception_handler(InvalidRunTransitionError)
    async def _transition_error(_: Request, exc: InvalidRunTransitionError) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"error": "invalid_transition", "detail": str(exc)}
        )

    @app.exception_handler(InvalidIdentifierError)
    async def _identifier_error(_: Request, exc: InvalidIdentifierError) -> JSONResponse:
        return JSONResponse(
            status_code=400, content={"error": "invalid_identifier", "detail": str(exc)}
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "detail": "request validation failed",
                "issues": [
                    {
                        "path": ".".join(str(p) for p in e.get("loc", ())),
                        "message": str(e.get("msg")),
                    }
                    for e in exc.errors()
                ],
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("api.unhandled_error", path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": "an internal error occurred"},
        )

    return app


app = create_app()

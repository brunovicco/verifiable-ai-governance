"""FastAPI composition root for the governance API."""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ai_governance_api.config import get_settings
from ai_governance_api.database import engine
from ai_governance_api.dependencies import (
    get_control_catalog,
    get_control_crosswalk,
    get_directory_authorization_catalog,
    get_runtime_control_projection,
)
from ai_governance_api.errors import ApplicationError, ErrorKind
from ai_governance_api.models import Base
from ai_governance_api.routers.assessments import router as assessments_router
from ai_governance_api.routers.authentication import router as authentication_router
from ai_governance_api.routers.controls import router as controls_router
from ai_governance_api.routers.dashboard import router as dashboard_router
from ai_governance_api.routers.evidence import router as evidence_router
from ai_governance_api.routers.health import router as health_router
from ai_governance_api.routers.incidents import router as incidents_router
from ai_governance_api.routers.initiatives import router as initiatives_router
from ai_governance_api.routers.inventory import router as inventory_router
from ai_governance_api.routers.model_routing import router as model_routing_router
from ai_governance_api.routers.runtime_control import router as runtime_control_router
from ai_governance_api.routers.runtime_telemetry import router as runtime_telemetry_router
from ai_governance_api.telemetry import (
    TraceContextMiddleware,
    configure_telemetry,
    shutdown_telemetry,
)

P1_5_DISTRIBUTED_RUNTIME_TRACING = True

ERROR_STATUS_CODES = {
    ErrorKind.FORBIDDEN: 403,
    ErrorKind.NOT_FOUND: 404,
    ErrorKind.CONFLICT: 409,
    ErrorKind.UNPROCESSABLE: 422,
    ErrorKind.PAYLOAD_TOO_LARGE: 413,
    ErrorKind.UNSUPPORTED_MEDIA_TYPE: 415,
    ErrorKind.DEPENDENCY_UNAVAILABLE: 503,
}


class RequestBodyTooLarge(Exception):
    """Signal that an HTTP body crossed its endpoint-specific byte limit."""


class EvidenceRequestSizeLimitMiddleware:
    """Reject oversized evidence requests before multipart parsing and temp spooling."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        """Initialize the ASGI middleware with a strict request-body bound."""
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Enforce Content-Length and streamed-byte bounds on evidence POSTs."""
        if not self._is_evidence_upload(scope):
            await self._app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
                if declared_length < 0 or declared_length > self._max_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await self._reject(scope, receive, send)
                return

        received_bytes = 0

        async def limited_receive() -> Message:
            """Count body chunks before forwarding them to the multipart parser."""
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self._max_bytes:
                    raise RequestBodyTooLarge
            return message

        try:
            await self._app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            await self._reject(scope, receive, send)

    @staticmethod
    def _is_evidence_upload(scope: Scope) -> bool:
        """Return whether the request targets the evidence multipart command."""
        path = str(scope.get("path", ""))
        return (
            scope["type"] == "http"
            and scope.get("method") == "POST"
            and path.startswith("/api/v1/initiatives/")
            and path.endswith("/evidence")
        )

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Return the stable payload-too-large transport response."""
        response = JSONResponse(
            status_code=413,
            content={"detail": "Evidence request exceeds the configured upload limit"},
        )
        await response(scope, receive, send)


def configure_logging(level: str) -> None:
    """Configure process logs as an unbuffered stdout event stream."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root_logger.addHandler(handler)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure telemetry, local schema bootstrap, and graceful resource shutdown."""
    settings = app.state.settings
    configure_telemetry(
        enabled=settings.otel_enabled,
        service_name="verifiable-ai-governance",
        service_version=settings.app_version,
        environment=settings.app_env.value,
        endpoint=settings.otel_endpoint,
        timeout_seconds=settings.otel_timeout_seconds,
    )
    if settings.auto_create_schema:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        await get_runtime_control_projection().close()
        shutdown_telemetry()
        await engine.dispose()


def create_app() -> FastAPI:
    """Build and configure the API application."""
    settings = get_settings()
    get_control_catalog()
    get_control_crosswalk()
    get_directory_authorization_catalog()
    configure_logging(settings.log_level)
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Risk-based and evidence-driven AI governance API",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        EvidenceRequestSizeLimitMiddleware,
        max_bytes=settings.evidence_max_bytes + settings.evidence_request_overhead_bytes,
    )
    app.add_middleware(TraceContextMiddleware)
    app.include_router(health_router)
    app.include_router(authentication_router)
    app.include_router(initiatives_router)
    app.include_router(assessments_router)
    app.include_router(controls_router)
    app.include_router(evidence_router)
    app.include_router(inventory_router)
    app.include_router(model_routing_router)
    app.include_router(runtime_control_router)
    app.include_router(runtime_telemetry_router)
    app.include_router(incidents_router)
    app.include_router(dashboard_router)

    @app.exception_handler(ApplicationError)
    async def handle_application_error(
        _: Request,
        exc: ApplicationError,
    ) -> JSONResponse:
        """Map application failures to the HTTP adapter's error contract."""
        return JSONResponse(
            status_code=ERROR_STATUS_CODES[exc.kind],
            content={"detail": exc.detail},
        )

    return app


app = create_app()

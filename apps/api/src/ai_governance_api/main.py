"""FastAPI composition root for the governance API."""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ai_governance_api.config import get_settings
from ai_governance_api.database import engine
from ai_governance_api.errors import ApplicationError, ErrorKind
from ai_governance_api.models import Base
from ai_governance_api.routers.health import router as health_router
from ai_governance_api.routers.initiatives import router as initiatives_router
from ai_governance_api.routers.inventory import router as inventory_router

ERROR_STATUS_CODES = {
    ErrorKind.FORBIDDEN: 403,
    ErrorKind.NOT_FOUND: 404,
    ErrorKind.CONFLICT: 409,
    ErrorKind.UNPROCESSABLE: 422,
}


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
    """Create local schemas when explicitly enabled and dispose resources on shutdown."""
    if app.state.settings.auto_create_schema:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Build and configure the API application."""
    settings = get_settings()
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
    app.include_router(health_router)
    app.include_router(initiatives_router)
    app.include_router(inventory_router)

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

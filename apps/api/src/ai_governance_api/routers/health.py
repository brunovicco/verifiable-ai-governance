"""Process liveness and dependency readiness endpoints."""

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ai_governance_api.database import engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

READINESS_TIMEOUT_SECONDS = 2.0


async def check_database_readiness() -> bool:
    """Return whether the configured database can execute a minimal query."""
    try:
        async with asyncio.timeout(READINESS_TIMEOUT_SECONDS):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except Exception as exc:
        # Do not expose connection details or exception messages through the endpoint.
        logger.warning(
            "Database readiness check failed",
            extra={
                "dependency": "database",
                "error_type": type(exc).__name__,
            },
        )
        return False
    return True


@router.get("/health", include_in_schema=False)
async def legacy_health() -> dict[str, str]:
    """Preserve the original health endpoint for backward compatibility."""
    return {"status": "ok"}


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Confirm that the API process is running and can serve HTTP requests."""
    return {"status": "ok"}


@router.get(
    "/health/ready",
    response_model=None,
    responses={
        503: {
            "description": "A required dependency is unavailable.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "unavailable",
                        "checks": {"database": "unavailable"},
                    }
                }
            },
        }
    },
)
async def readiness() -> dict[str, object] | JSONResponse:
    """Confirm that required dependencies are available before receiving traffic."""
    if not await check_database_readiness():
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "checks": {"database": "unavailable"},
            },
        )
    return {
        "status": "ok",
        "checks": {"database": "ok"},
    }

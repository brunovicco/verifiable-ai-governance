"""Process liveness and fail-closed runtime readiness endpoints."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ai_governance_api.adapters.runtime_readiness import check_runtime_readiness

router = APIRouter(tags=["health"])


@router.get("/health", include_in_schema=False)
async def legacy_health() -> dict[str, str]:
    """Preserve the original process-only endpoint for compatibility."""
    return {"status": "ok"}


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Confirm that the API process can serve HTTP requests."""
    return {"status": "ok"}


@router.get(
    "/health/ready",
    response_model=None,
    responses={
        503: {
            "description": "A required runtime check failed.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "unavailable",
                        "checks": {
                            "database": "ok",
                            "schema": "mismatch",
                        },
                    }
                }
            },
        }
    },
)
async def readiness() -> dict[str, object] | JSONResponse:
    """Confirm database access and exact Alembic-head compatibility."""
    report = await check_runtime_readiness()
    content: dict[str, object] = {
        "status": "ok" if report.ready else "unavailable",
        "checks": report.public_checks(),
    }
    if not report.ready:
        return JSONResponse(status_code=503, content=content)
    return content

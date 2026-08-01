"""Process health endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Confirm that the API process can serve requests."""
    return {"status": "ok"}

"""HTTP adapter for the portfolio-wide governance dashboard."""

from fastapi import APIRouter

from ai_governance_api.dashboard_schemas import DashboardRead
from ai_governance_api.dependencies import BuildDashboardSnapshotDependency, CurrentPrincipal

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardRead)
async def get_dashboard(
    use_case: BuildDashboardSnapshotDependency,
    _: CurrentPrincipal,
) -> DashboardRead:
    """Return a portfolio-wide monitoring snapshot for any authenticated principal."""
    snapshot = await use_case.execute()
    return DashboardRead.from_domain(snapshot)

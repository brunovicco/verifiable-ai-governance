"""FastAPI adapter for the versioned governance control catalog."""

from fastapi import APIRouter
from governance_schemas import ControlCatalog, ControlCrosswalk, InitiativeControlReport

from ai_governance_api.dependencies import (
    CurrentPrincipal,
    EvaluateInitiativeControlsDependency,
    GetControlCrosswalkDependency,
    ListControlCatalogDependency,
)

router = APIRouter(prefix="/api/v1", tags=["controls"])


@router.get("/controls", response_model=ControlCatalog)
async def list_control_catalog(
    use_case: ListControlCatalogDependency,
    _: CurrentPrincipal,
) -> ControlCatalog:
    """Return the active catalog and its versioned definitions."""
    return use_case.execute()


@router.get("/controls/crosswalk", response_model=ControlCrosswalk)
async def get_control_crosswalk(
    use_case: GetControlCrosswalkDependency,
    _: CurrentPrincipal,
) -> ControlCrosswalk:
    """Return the non-authoritative external-framework crosswalk."""
    return use_case.execute()


@router.get(
    "/initiatives/{initiative_id}/controls",
    response_model=InitiativeControlReport,
)
async def evaluate_initiative_controls(
    initiative_id: str,
    use_case: EvaluateInitiativeControlsDependency,
    _: CurrentPrincipal,
) -> InitiativeControlReport:
    """Return explainable applicability for every control in an initiative."""
    return await use_case.execute(initiative_id)

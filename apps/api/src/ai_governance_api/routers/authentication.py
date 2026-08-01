"""Authenticated-principal inspection endpoint."""

from fastapi import APIRouter

from ai_governance_api.dependencies import CurrentPrincipal
from ai_governance_api.schemas import PrincipalRead

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.get("/me", response_model=PrincipalRead)
async def current_identity(principal: CurrentPrincipal) -> PrincipalRead:
    """Return the caller identity and mapped governance capabilities."""
    directory_identity = principal.directory_identity
    return PrincipalRead(
        user_id=principal.user_id,
        email=principal.email,
        approval_areas=sorted(principal.approval_areas, key=lambda area: area.value),
        is_admin=principal.is_admin,
        tenant_id=directory_identity.tenant_id if directory_identity else None,
        object_id=directory_identity.object_id if directory_identity else None,
        account_type=directory_identity.account_type if directory_identity else None,
    )

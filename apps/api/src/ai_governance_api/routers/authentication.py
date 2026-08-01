"""Authenticated-principal inspection endpoint."""

from fastapi import APIRouter

from ai_governance_api.dependencies import CurrentCorporateDirectoryProfile, CurrentPrincipal
from ai_governance_api.schemas import CorporateDirectoryProfileRead, PrincipalRead

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.get("/me", response_model=PrincipalRead)
async def current_identity(
    principal: CurrentPrincipal,
    directory_profile: CurrentCorporateDirectoryProfile,
) -> PrincipalRead:
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
        directory_profile=(
            CorporateDirectoryProfileRead(
                display_name=directory_profile.display_name,
                email_or_upn=directory_profile.email_or_upn,
                department=directory_profile.department,
                user_type=directory_profile.user_type,
            )
            if directory_profile is not None
            else None
        ),
    )

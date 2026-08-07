"""Authenticated-principal inspection endpoint."""

from fastapi import APIRouter

from ai_governance_api.dependencies import (
    BlockDirectoryAccessDependency,
    CurrentAuthorizedPrincipal,
    CurrentCorporateDirectoryProfile,
    CurrentPrincipal,
    InvalidateDirectoryAuthorizationDependency,
    RestoreDirectoryAccessDependency,
)
from ai_governance_api.schemas import (
    AuthorizationProvenanceRead,
    CorporateDirectoryProfileRead,
    DirectoryAccessBlockRequest,
    DirectoryAccessRestoreRequest,
    DirectoryAccessStateRead,
    DirectoryAuthorizationCacheInvalidationRead,
    DirectoryAuthorizationCacheInvalidationRequest,
    PrincipalRead,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.post("/directory-access/block", response_model=DirectoryAccessStateRead)
async def block_directory_access(
    request: DirectoryAccessBlockRequest,
    principal: CurrentPrincipal,
    command: BlockDirectoryAccessDependency,
) -> DirectoryAccessStateRead:
    """Suspend one Entra identity immediately through an audited admin action."""
    state = await command.execute(
        tenant_id=str(request.tenant_id),
        object_id=str(request.object_id),
        reason=request.reason,
        reference=request.reference,
        actor=principal,
    )
    return DirectoryAccessStateRead(
        restriction_id=state.target.entry_id,
        blocked=state.blocked,
        changed_at=state.changed_at,
        version=state.version,
    )


@router.post("/directory-access/restore", response_model=DirectoryAccessStateRead)
async def restore_directory_access(
    request: DirectoryAccessRestoreRequest,
    principal: CurrentPrincipal,
    command: RestoreDirectoryAccessDependency,
) -> DirectoryAccessStateRead:
    """Restore one Entra identity while forcing fresh authorization resolution."""
    state = await command.execute(
        tenant_id=str(request.tenant_id),
        object_id=str(request.object_id),
        reason=request.reason,
        reference=request.reference,
        actor=principal,
    )
    return DirectoryAccessStateRead(
        restriction_id=state.target.entry_id,
        blocked=state.blocked,
        changed_at=state.changed_at,
        version=state.version,
    )


@router.post(
    "/directory-authorization-cache/invalidate",
    response_model=DirectoryAuthorizationCacheInvalidationRead,
)
async def invalidate_directory_authorization_cache(
    request: DirectoryAuthorizationCacheInvalidationRequest,
    principal: CurrentPrincipal,
    command: InvalidateDirectoryAuthorizationDependency,
) -> DirectoryAuthorizationCacheInvalidationRead:
    """Invalidate one Entra authorization snapshot through an audited admin action."""
    invalidation = await command.execute(
        tenant_id=str(request.tenant_id),
        object_id=str(request.object_id),
        reason=request.reason,
        reference=request.reference,
        actor=principal,
    )
    return DirectoryAuthorizationCacheInvalidationRead(
        cache_entry_id=invalidation.key.entry_id,
        invalidated_at=invalidation.invalidated_at,
        version=invalidation.version,
    )


@router.get("/me", response_model=PrincipalRead)
async def current_identity(
    principal: CurrentAuthorizedPrincipal,
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
        authorization_provenance=(
            AuthorizationProvenanceRead(
                catalog_id=principal.authorization_provenance.catalog_id,
                catalog_version=principal.authorization_provenance.catalog_version,
                catalog_digest=principal.authorization_provenance.catalog_digest,
                matched_mapping_ids=list(principal.authorization_provenance.matched_mapping_ids),
                source_types=list(principal.authorization_provenance.source_types),
                group_resolution_source=(
                    principal.authorization_provenance.group_resolution_source
                ),
            )
            if principal.authorization_provenance is not None
            else None
        ),
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

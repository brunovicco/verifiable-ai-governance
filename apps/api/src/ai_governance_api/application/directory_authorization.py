"""Use case for resolving effective corporate approval capabilities."""

from ai_governance_api.domain.directory_authorization import DirectoryAuthorizationCatalog
from ai_governance_api.domain.identity import DirectoryGroupResolutionSource, Principal


class ResolveDirectoryAuthorization:
    """Apply one immutable directory authorization catalog to a principal."""

    def __init__(
        self,
        catalog: DirectoryAuthorizationCatalog,
        *,
        guest_approvals_enabled: bool,
    ) -> None:
        """Initialize the resolver with explicit guest policy."""
        self._catalog = catalog
        self._guest_approvals_enabled = guest_approvals_enabled

    def execute(
        self,
        principal: Principal,
        *,
        group_object_ids: frozenset[str] = frozenset(),
        group_resolution_source: DirectoryGroupResolutionSource = (
            DirectoryGroupResolutionSource.NONE
        ),
    ) -> Principal:
        """Return a principal with catalog-derived effective approval areas."""
        return self._catalog.authorize(
            principal,
            group_object_ids=group_object_ids,
            group_resolution_source=group_resolution_source,
            guest_approvals_enabled=self._guest_approvals_enabled,
        )

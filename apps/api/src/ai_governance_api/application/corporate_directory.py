"""Corporate-directory enrichment contracts and identity-binding use case."""

from dataclasses import dataclass, field
from typing import Protocol

from ai_governance_api.domain.identity import DirectoryIdentity, Principal


class CorporateDirectoryError(Exception):
    """Base class for safe corporate-directory failures."""


class CorporateDirectoryNotApplicable(CorporateDirectoryError):
    """Raised when a principal has no trusted corporate-directory identity."""


class CorporateDirectoryIdentityMismatch(CorporateDirectoryError):
    """Raised when directory data does not match the authenticated identity."""


class CorporateDirectoryUnavailable(CorporateDirectoryError):
    """Raised when the identity provider or directory cannot complete enrichment."""

    def __init__(self, *, retry_after_seconds: int | None = None) -> None:
        """Initialize the failure with an optional bounded retry delay."""
        super().__init__("Corporate directory unavailable")
        self.retry_after_seconds = retry_after_seconds


class CorporateDirectoryResponseInvalid(CorporateDirectoryError):
    """Raised when a directory response violates the expected minimal contract."""


@dataclass(frozen=True, slots=True)
class CorporateDirectoryProfile:
    """Minimal directory snapshot resolved for the authenticated user."""

    tenant_id: str
    object_id: str
    display_name: str | None = None
    email_or_upn: str | None = None
    department: str | None = None
    user_type: str | None = None
    group_object_ids: frozenset[str] = field(default_factory=frozenset)


class CorporateDirectoryPort(Protocol):
    """Port for delegated corporate-directory profile resolution."""

    async def resolve(
        self,
        user_assertion: str,
        expected_identity: DirectoryIdentity,
    ) -> CorporateDirectoryProfile:
        """Resolve the current user without persisting the delegated credential."""
        ...


class ResolveCorporateDirectory:
    """Bind delegated directory data to the already authenticated principal."""

    def __init__(self, directory: CorporateDirectoryPort) -> None:
        """Initialize the use case with a consumer-owned directory port."""
        self._directory = directory

    async def execute(
        self,
        principal: Principal,
        user_assertion: str,
    ) -> CorporateDirectoryProfile:
        """Resolve and verify a minimal profile for a trusted Entra principal."""
        identity = principal.directory_identity
        if identity is None:
            raise CorporateDirectoryNotApplicable(
                "Corporate directory enrichment requires a trusted directory identity"
            )
        if not user_assertion.strip():
            raise CorporateDirectoryUnavailable()

        profile = await self._directory.resolve(user_assertion, identity)
        if profile.tenant_id != identity.tenant_id or profile.object_id != identity.object_id:
            raise CorporateDirectoryIdentityMismatch(
                "Directory profile does not match the authenticated principal"
            )
        return profile

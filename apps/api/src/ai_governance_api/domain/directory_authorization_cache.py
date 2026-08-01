"""Pure freshness and identity-binding rules for authorization snapshots."""

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from governance_schemas import ApprovalArea

from ai_governance_api.domain.identity import (
    AuthorizationProvenance,
    DirectoryGroupResolutionSource,
    DirectoryIdentity,
    Principal,
)


class DirectoryAuthorizationCacheError(ValueError):
    """Raised when a cached authorization snapshot cannot be trusted."""


class DirectoryAuthorizationInvalidationReason(StrEnum):
    """Bounded operational reasons accepted by the invalidation command."""

    ACCESS_REMOVED = "access_removed"
    ROLE_CHANGED = "role_changed"
    GROUP_CHANGED = "group_changed"
    INCIDENT_RESPONSE = "incident_response"
    CATALOG_CHANGED = "catalog_changed"
    MANUAL_REVALIDATION = "manual_revalidation"


@dataclass(frozen=True, slots=True)
class DirectoryAuthorizationCacheKey:
    """Stable cache key scoped by Entra tenant and directory object."""

    tenant_id: str
    object_id: str

    def __post_init__(self) -> None:
        """Canonicalize both non-nil UUID components."""
        object.__setattr__(self, "tenant_id", _canonical_uuid(self.tenant_id, "tenant ID"))
        object.__setattr__(self, "object_id", _canonical_uuid(self.object_id, "object ID"))

    @classmethod
    def from_identity(
        cls,
        identity: DirectoryIdentity,
    ) -> "DirectoryAuthorizationCacheKey":
        """Create a key from an already authenticated directory identity."""
        return cls(tenant_id=identity.tenant_id, object_id=identity.object_id)

    @property
    def entry_id(self) -> str:
        """Return a deterministic opaque UUID suitable for persistence and audit."""
        return str(
            uuid5(
                NAMESPACE_URL,
                f"verifiable-ai-governance:directory-authorization:{self.tenant_id}:{self.object_id}",
            )
        )

    @property
    def target_digest(self) -> str:
        """Return a non-reversible identity reference for minimized audit payloads."""
        canonical = f"{self.tenant_id}:{self.object_id}".encode()
        return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class DirectoryAuthorizationSnapshot:
    """Minimal derived authorization state with an explicit validity interval."""

    key: DirectoryAuthorizationCacheKey
    approval_areas: frozenset[ApprovalArea]
    catalog_id: str
    catalog_version: str
    catalog_digest: str
    resolved_at: datetime
    expires_at: datetime
    matched_mapping_ids: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    original_group_resolution_source: DirectoryGroupResolutionSource = (
        DirectoryGroupResolutionSource.NONE
    )
    invalidated_at: datetime | None = None
    version: int = 1

    def __post_init__(self) -> None:
        """Reject malformed, timeless, or internally inconsistent snapshots."""
        if not self.catalog_id.strip() or len(self.catalog_id) > 100:
            raise DirectoryAuthorizationCacheError("Catalog ID is invalid")
        if not self.catalog_version.strip() or len(self.catalog_version) > 50:
            raise DirectoryAuthorizationCacheError("Catalog version is invalid")
        if re.fullmatch(r"[a-f0-9]{64}", self.catalog_digest) is None:
            raise DirectoryAuthorizationCacheError("Catalog digest is invalid")
        if len(self.approval_areas) > len(ApprovalArea) or any(
            not isinstance(area, ApprovalArea) for area in self.approval_areas
        ):
            raise DirectoryAuthorizationCacheError("Approval areas are invalid")
        if (
            len(self.matched_mapping_ids) > 1000
            or len(self.matched_mapping_ids) != len(set(self.matched_mapping_ids))
            or any(
                not mapping_id
                or len(mapping_id) > 100
                or re.fullmatch(r"[a-z0-9][a-z0-9._-]*", mapping_id) is None
                for mapping_id in self.matched_mapping_ids
            )
        ):
            raise DirectoryAuthorizationCacheError("Matched mapping IDs are invalid")
        if (
            len(self.source_types) > 2
            or len(self.source_types) != len(set(self.source_types))
            or not set(self.source_types).issubset({"app_role", "group"})
        ):
            raise DirectoryAuthorizationCacheError("Authorization source types are invalid")
        if self.original_group_resolution_source not in {
            DirectoryGroupResolutionSource.NONE,
            DirectoryGroupResolutionSource.TOKEN,
            DirectoryGroupResolutionSource.MICROSOFT_GRAPH,
        }:
            raise DirectoryAuthorizationCacheError(
                "Original group resolution source is invalid"
            )
        _require_aware(self.resolved_at, "resolved_at")
        _require_aware(self.expires_at, "expires_at")
        if self.expires_at <= self.resolved_at:
            raise DirectoryAuthorizationCacheError(
                "Authorization snapshot expiry must follow its resolution"
            )
        if self.invalidated_at is not None:
            _require_aware(self.invalidated_at, "invalidated_at")
        if self.version < 1:
            raise DirectoryAuthorizationCacheError("Snapshot version must be positive")

    def is_fresh(self, *, now: datetime, catalog_digest: str) -> bool:
        """Return whether the snapshot is current for time, policy, and invalidation."""
        _require_aware(now, "now")
        return (
            self.catalog_digest == catalog_digest
            and now < self.expires_at
            and (
                self.invalidated_at is None
                or self.resolved_at > self.invalidated_at
            )
        )

    def authorize(self, principal: Principal) -> Principal:
        """Apply the snapshot only to the exact authenticated directory identity."""
        identity = principal.directory_identity
        if identity is None or DirectoryAuthorizationCacheKey.from_identity(identity) != self.key:
            raise DirectoryAuthorizationCacheError(
                "Authorization snapshot does not match the authenticated identity"
            )
        provenance = AuthorizationProvenance(
            catalog_id=self.catalog_id,
            catalog_version=self.catalog_version,
            catalog_digest=self.catalog_digest,
            matched_mapping_ids=self.matched_mapping_ids,
            source_types=self.source_types,
            group_resolution_source=DirectoryGroupResolutionSource.CACHE,
        )
        return replace(
            principal,
            approval_areas=self.approval_areas,
            authorization_provenance=provenance,
        )


@dataclass(frozen=True, slots=True)
class DirectoryAuthorizationInvalidation:
    """Result of a shared authorization-cache invalidation command."""

    key: DirectoryAuthorizationCacheKey
    invalidated_at: datetime
    version: int

    def __post_init__(self) -> None:
        """Require an aware timestamp and a positive persisted version."""
        _require_aware(self.invalidated_at, "invalidated_at")
        if self.version < 1:
            raise DirectoryAuthorizationCacheError("Invalidation version must be positive")


def _canonical_uuid(value: str, label: str) -> str:
    """Return a canonical non-nil UUID or reject an unsafe cache key."""
    try:
        parsed = UUID(value.strip())
    except (ValueError, AttributeError) as exc:
        raise DirectoryAuthorizationCacheError(f"{label} must be a UUID") from exc
    if parsed.int == 0:
        raise DirectoryAuthorizationCacheError(f"{label} must be non-nil")
    return str(parsed)


def _require_aware(value: datetime, label: str) -> None:
    """Reject naive timestamps because freshness must be timezone-independent."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise DirectoryAuthorizationCacheError(f"{label} must be timezone-aware")

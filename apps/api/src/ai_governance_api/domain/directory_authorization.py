"""Pure, deterministic authorization mapping for corporate directory identities."""

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from enum import StrEnum
from uuid import UUID

from governance_schemas import ApprovalArea

from ai_governance_api.domain.identity import (
    AuthorizationProvenance,
    DirectoryAccountType,
    DirectoryGroupResolutionSource,
    Principal,
)


class DirectoryAuthorizationError(ValueError):
    """Raised when authorization policy data cannot be trusted."""


class DirectoryAuthorizationSource(StrEnum):
    """Supported stable sources for corporate approval capabilities."""

    APP_ROLE = "app_role"
    GROUP = "group"


@dataclass(frozen=True, slots=True)
class DirectoryAuthorizationMapping:
    """One versioned mapping from a stable Entra value to an approval area."""

    mapping_id: str
    tenant_id: str
    source_type: DirectoryAuthorizationSource
    source_value: str
    approval_area: ApprovalArea
    enabled: bool
    owner: str
    mapping_version: int

    def __post_init__(self) -> None:
        """Normalize stable identifiers and reject ambiguous mapping data."""
        mapping_id = self.mapping_id.strip()
        owner = self.owner.strip()
        source_value = self.source_value.strip()
        _validate_public_identifier(mapping_id, "Mapping ID", max_length=100)
        if not owner or len(owner) > 200:
            raise DirectoryAuthorizationError("Mapping owner must contain 1 to 200 characters")
        if self.mapping_version < 1:
            raise DirectoryAuthorizationError("Mapping version must be positive")
        if not source_value or len(source_value) > 256:
            raise DirectoryAuthorizationError(
                "Mapping source value must contain 1 to 256 characters"
            )
        object.__setattr__(self, "mapping_id", mapping_id)
        object.__setattr__(self, "owner", owner)
        object.__setattr__(self, "tenant_id", _canonical_uuid(self.tenant_id, "tenant ID"))
        object.__setattr__(
            self,
            "source_value",
            (
                _canonical_uuid(source_value, "group object ID")
                if self.source_type is DirectoryAuthorizationSource.GROUP
                else source_value
            ),
        )


@dataclass(frozen=True, slots=True)
class DirectoryAuthorizationCatalog:
    """Immutable policy catalog evaluated without I/O or mutable state."""

    catalog_id: str
    catalog_version: str
    mappings: tuple[DirectoryAuthorizationMapping, ...]
    catalog_digest: str = field(init=False)

    def __post_init__(self) -> None:
        """Reject empty metadata and duplicate mapping definitions."""
        catalog_id = self.catalog_id.strip()
        catalog_version = self.catalog_version.strip()
        _validate_public_identifier(catalog_id, "Catalog ID", max_length=100)
        _validate_public_identifier(catalog_version, "Catalog version", max_length=50)
        if len(self.mappings) > 1000:
            raise DirectoryAuthorizationError("Catalog exceeds its mapping limit")
        mapping_ids = [mapping.mapping_id for mapping in self.mappings]
        if len(mapping_ids) != len(set(mapping_ids)):
            raise DirectoryAuthorizationError("Mapping IDs must be unique")
        identities = [
            (
                mapping.tenant_id,
                mapping.source_type,
                mapping.source_value,
                mapping.approval_area,
            )
            for mapping in self.mappings
        ]
        if len(identities) != len(set(identities)):
            raise DirectoryAuthorizationError("Authorization mappings must be unique")
        object.__setattr__(self, "catalog_id", catalog_id)
        object.__setattr__(self, "catalog_version", catalog_version)
        canonical = json.dumps(
            {
                "catalog_id": catalog_id,
                "catalog_version": catalog_version,
                "mappings": [
                    {
                        "mapping_id": mapping.mapping_id,
                        "tenant_id": mapping.tenant_id,
                        "source_type": mapping.source_type.value,
                        "source_value": mapping.source_value,
                        "approval_area": mapping.approval_area.value,
                        "enabled": mapping.enabled,
                        "owner": mapping.owner,
                        "mapping_version": mapping.mapping_version,
                    }
                    for mapping in sorted(self.mappings, key=lambda item: item.mapping_id)
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        object.__setattr__(
            self,
            "catalog_digest",
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    def authorize(
        self,
        principal: Principal,
        *,
        group_object_ids: frozenset[str],
        group_resolution_source: DirectoryGroupResolutionSource,
        guest_approvals_enabled: bool,
    ) -> Principal:
        """Return effective capabilities and minimized catalog provenance."""
        identity = principal.directory_identity
        if identity is None:
            return principal
        groups = frozenset(
            _canonical_uuid(group_id, "resolved group object ID") for group_id in group_object_ids
        )
        if groups and group_resolution_source in {
            DirectoryGroupResolutionSource.NONE,
            DirectoryGroupResolutionSource.OVERAGE_UNRESOLVED,
        }:
            raise DirectoryAuthorizationError("Resolved groups require a trusted resolution source")
        eligible = identity.account_type is DirectoryAccountType.MEMBER or (
            identity.account_type is DirectoryAccountType.GUEST and guest_approvals_enabled
        )
        matched = (
            tuple(
                mapping
                for mapping in self.mappings
                if mapping.enabled
                and mapping.tenant_id == identity.tenant_id
                and _mapping_matches(mapping, principal.directory_role_values, groups)
            )
            if eligible
            else ()
        )
        provenance = AuthorizationProvenance(
            catalog_id=self.catalog_id,
            catalog_version=self.catalog_version,
            catalog_digest=self.catalog_digest,
            matched_mapping_ids=tuple(sorted(mapping.mapping_id for mapping in matched)),
            source_types=tuple(sorted({mapping.source_type.value for mapping in matched})),
            group_resolution_source=group_resolution_source,
        )
        return replace(
            principal,
            approval_areas=frozenset(mapping.approval_area for mapping in matched),
            authorization_provenance=provenance,
        )


def _mapping_matches(
    mapping: DirectoryAuthorizationMapping,
    role_values: frozenset[str],
    group_object_ids: frozenset[str],
) -> bool:
    """Compare exact role values or canonical group IDs without display names."""
    if mapping.source_type is DirectoryAuthorizationSource.APP_ROLE:
        return mapping.source_value in role_values
    return mapping.source_value in group_object_ids


def _canonical_uuid(value: str, label: str) -> str:
    """Return a canonical non-nil UUID for a stable directory identifier."""
    try:
        parsed = UUID(value.strip())
    except (ValueError, AttributeError) as exc:
        raise DirectoryAuthorizationError(f"{label} must be a UUID") from exc
    if parsed.int == 0:
        raise DirectoryAuthorizationError(f"{label} must be non-nil")
    return str(parsed)


def _validate_public_identifier(value: str, label: str, *, max_length: int) -> None:
    """Require a bounded opaque identifier safe for APIs and audit events."""
    if len(value) > max_length or re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value) is None:
        raise DirectoryAuthorizationError(
            f"{label} must use lowercase letters, numbers, dots, underscores or hyphens"
        )

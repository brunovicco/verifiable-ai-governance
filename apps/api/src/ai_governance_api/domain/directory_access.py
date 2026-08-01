"""Pure rules for emergency access restrictions on corporate identities."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from ai_governance_api.domain.identity import DirectoryIdentity


class DirectoryAccessError(ValueError):
    """Raised when an emergency directory-access record cannot be trusted."""


class DirectoryAccessBlockReason(StrEnum):
    """Bounded incident reasons accepted when suspending platform access."""

    ACCOUNT_COMPROMISED = "account_compromised"
    PERSONNEL_OFFBOARDING = "personnel_offboarding"
    INCIDENT_RESPONSE = "incident_response"
    POLICY_VIOLATION = "policy_violation"
    MANUAL_EMERGENCY = "manual_emergency"


class DirectoryAccessRestoreReason(StrEnum):
    """Bounded reasons accepted when restoring platform access."""

    REMEDIATION_COMPLETED = "remediation_completed"
    FALSE_POSITIVE = "false_positive"
    ACCESS_REINSTATED = "access_reinstated"


type DirectoryAccessChangeReason = (
    DirectoryAccessBlockReason | DirectoryAccessRestoreReason
)


@dataclass(frozen=True, slots=True)
class DirectoryAccessTarget:
    """Stable Entra identity target scoped by tenant and directory object."""

    tenant_id: str
    object_id: str

    def __post_init__(self) -> None:
        """Canonicalize both non-nil UUID components."""
        object.__setattr__(self, "tenant_id", _canonical_uuid(self.tenant_id, "tenant ID"))
        object.__setattr__(self, "object_id", _canonical_uuid(self.object_id, "object ID"))

    @classmethod
    def from_identity(cls, identity: DirectoryIdentity) -> "DirectoryAccessTarget":
        """Create a target from an already authenticated directory identity."""
        return cls(tenant_id=identity.tenant_id, object_id=identity.object_id)

    @property
    def entry_id(self) -> str:
        """Return a deterministic opaque UUID suitable for persistence and audit."""
        return str(
            uuid5(
                NAMESPACE_URL,
                f"verifiable-ai-governance:directory-access:{self.tenant_id}:{self.object_id}",
            )
        )

    @property
    def target_digest(self) -> str:
        """Return a non-reversible target reference for minimized audit payloads."""
        canonical = f"{self.tenant_id}:{self.object_id}".encode()
        return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class DirectoryAccessState:
    """Current platform access state for one stable directory identity."""

    target: DirectoryAccessTarget
    blocked: bool
    changed_at: datetime
    version: int

    def __post_init__(self) -> None:
        """Reject timeless or unversioned access state."""
        if self.changed_at.tzinfo is None or self.changed_at.utcoffset() is None:
            raise DirectoryAccessError("changed_at must be timezone-aware")
        if self.version < 1:
            raise DirectoryAccessError("Directory access version must be positive")


def _canonical_uuid(value: str, label: str) -> str:
    """Return a canonical non-nil UUID or reject an unsafe identity target."""
    try:
        parsed = UUID(value.strip())
    except (ValueError, AttributeError) as exc:
        raise DirectoryAccessError(f"{label} must be a UUID") from exc
    if parsed.int == 0:
        raise DirectoryAccessError(f"{label} must be non-nil")
    return str(parsed)

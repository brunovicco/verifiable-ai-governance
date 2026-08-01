"""Pure identity types and claim-mapping policies."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from governance_schemas import ApprovalArea


class IdentityMappingError(Exception):
    """Raised when verified claims cannot produce a trusted principal."""


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated identity and its governance approval capabilities."""

    user_id: str
    email: str | None = None
    approval_areas: frozenset[ApprovalArea] = field(default_factory=frozenset)
    is_admin: bool = False


def principal_from_claims(
    claims: Mapping[str, object],
    *,
    areas_claim: str,
    admin_claim: str,
) -> Principal:
    """Map verified OIDC claims into the least-privileged domain identity."""
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise IdentityMappingError("OIDC subject missing")
    email_value = claims.get("email")
    email = email_value.strip() if isinstance(email_value, str) else None
    return Principal(
        user_id=subject.strip(),
        email=email or None,
        approval_areas=parse_approval_areas(_claim_at_path(claims, areas_claim)),
        is_admin=_claim_at_path(claims, admin_claim) is True,
    )


def parse_approval_areas(raw_areas: object) -> frozenset[ApprovalArea]:
    """Return known governance areas while ignoring unrelated provider roles."""
    if isinstance(raw_areas, str):
        values = raw_areas.split(",")
    elif isinstance(raw_areas, list):
        values = [str(item) for item in raw_areas]
    else:
        values = []
    parsed: set[ApprovalArea] = set()
    for value in values:
        try:
            parsed.add(ApprovalArea(value.strip().lower()))
        except ValueError:
            continue
    return frozenset(parsed)


def _claim_at_path(claims: Mapping[str, object], path: str) -> object:
    """Resolve a dot-separated claim path without interpreting array syntax."""
    current: object = claims
    for segment in path.split("."):
        if not segment or not isinstance(current, Mapping):
            return None
        current = current.get(segment)
    return current

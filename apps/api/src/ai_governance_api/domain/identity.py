"""Pure identity types and claim-mapping policies."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

from governance_schemas import ApprovalArea


class IdentityMappingError(Exception):
    """Raised when verified claims cannot produce a trusted principal."""


class DirectoryAccountType(StrEnum):
    """Account classifications relevant to corporate authorization."""

    MEMBER = "member"
    GUEST = "guest"
    UNKNOWN = "unknown"


class DirectoryGroupClaimState(StrEnum):
    """Trust state of group object IDs carried by a verified Entra token."""

    ABSENT = "absent"
    COMPLETE = "complete"
    OVERAGE = "overage"


class DirectoryGroupResolutionSource(StrEnum):
    """Content-minimized source used to resolve corporate group membership."""

    NONE = "none"
    TOKEN = "token"
    MICROSOFT_GRAPH = "microsoft_graph"
    CACHE = "cache"
    OVERAGE_UNRESOLVED = "overage_unresolved"


@dataclass(frozen=True, slots=True)
class DirectoryGroupClaims:
    """Bounded group object IDs and their completeness state from one token."""

    state: DirectoryGroupClaimState = DirectoryGroupClaimState.ABSENT
    object_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        """Prevent incomplete claim states from carrying authorization inputs."""
        if self.state is not DirectoryGroupClaimState.COMPLETE and self.object_ids:
            raise IdentityMappingError("Incomplete OIDC group claims cannot contain object IDs")


@dataclass(frozen=True, slots=True)
class DirectoryIdentity:
    """Stable corporate directory identity scoped by tenant."""

    tenant_id: str
    object_id: str
    account_type: DirectoryAccountType

    @property
    def key(self) -> str:
        """Return the stable compound key used by audit and ownership policies."""
        return f"{self.tenant_id}:{self.object_id}"


@dataclass(frozen=True, slots=True)
class CorporateIdentityPolicy:
    """Trusted tenant and guest-capability policy for corporate claims."""

    allowed_tenant_ids: frozenset[str]
    issuer_tenant_id: str
    guest_approvals_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated identity and its governance approval capabilities."""

    user_id: str
    email: str | None = None
    approval_areas: frozenset[ApprovalArea] = field(default_factory=frozenset)
    is_admin: bool = False
    directory_identity: DirectoryIdentity | None = None
    directory_role_values: frozenset[str] = field(default_factory=frozenset)
    directory_group_claims: DirectoryGroupClaims = field(default_factory=DirectoryGroupClaims)
    authorization_provenance: "AuthorizationProvenance | None" = None


@dataclass(frozen=True, slots=True)
class AuthorizationProvenance:
    """Content-minimized evidence for a resolved authorization decision."""

    catalog_id: str
    catalog_version: str
    catalog_digest: str
    matched_mapping_ids: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    group_resolution_source: DirectoryGroupResolutionSource = DirectoryGroupResolutionSource.NONE


def principal_from_claims(
    claims: Mapping[str, object],
    *,
    areas_claim: str,
    admin_claim: str,
    corporate_policy: CorporateIdentityPolicy | None = None,
    corporate_roles_claim: str | None = None,
    corporate_groups_claim: str | None = None,
) -> Principal:
    """Map verified OIDC claims into the least-privileged domain identity."""
    directory_identity = (
        _directory_identity_from_claims(claims, corporate_policy)
        if corporate_policy is not None
        else None
    )
    user_id = directory_identity.key if directory_identity else _subject_from_claims(claims)
    email_value = claims.get("email")
    email = email_value.strip() if isinstance(email_value, str) else None
    raw_areas = _claim_at_path(claims, areas_claim)
    raw_directory_roles = (
        _claim_at_path(claims, corporate_roles_claim)
        if directory_identity is not None and corporate_roles_claim is not None
        else raw_areas
    )
    approval_areas = (
        frozenset() if directory_identity is not None else parse_approval_areas(raw_areas)
    )
    directory_role_values = (
        _directory_role_values(raw_directory_roles)
        if directory_identity is not None
        else frozenset()
    )
    directory_group_claims = (
        _directory_group_claims(claims, corporate_groups_claim)
        if directory_identity is not None and corporate_groups_claim is not None
        else DirectoryGroupClaims()
    )
    is_admin = _claim_at_path(claims, admin_claim) is True
    if (
        directory_identity is not None
        and corporate_policy is not None
        and not _can_receive_approval_areas(
            directory_identity.account_type,
            corporate_policy,
        )
    ):
        approval_areas = frozenset()
    if (
        directory_identity is not None
        and directory_identity.account_type is not DirectoryAccountType.MEMBER
    ):
        is_admin = False
    return Principal(
        user_id=user_id,
        email=email or None,
        approval_areas=approval_areas,
        is_admin=is_admin,
        directory_identity=directory_identity,
        directory_role_values=directory_role_values,
        directory_group_claims=directory_group_claims,
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


def _directory_role_values(raw_roles: object) -> frozenset[str]:
    """Return bounded case-sensitive App Role values from a verified claim."""
    if isinstance(raw_roles, str):
        values = [raw_roles]
    elif isinstance(raw_roles, list) and all(isinstance(value, str) for value in raw_roles):
        values = raw_roles
    elif raw_roles is None:
        return frozenset()
    else:
        raise IdentityMappingError("OIDC App Roles claim is invalid")
    if len(values) > 128:
        raise IdentityMappingError("OIDC App Roles claim exceeds its item limit")
    normalized: set[str] = set()
    for value in values:
        role = value.strip()
        if len(role) > 256:
            raise IdentityMappingError("OIDC App Role value exceeds its size limit")
        if role:
            normalized.add(role)
    return frozenset(normalized)


def _directory_group_claims(
    claims: Mapping[str, object],
    claim_path: str,
) -> DirectoryGroupClaims:
    """Return complete token groups or an explicit overage state without remote URLs."""
    if _has_group_overage(claims):
        return DirectoryGroupClaims(state=DirectoryGroupClaimState.OVERAGE)

    raw_groups = _claim_at_path(claims, claim_path)
    if raw_groups is None:
        return DirectoryGroupClaims()
    if not isinstance(raw_groups, list) or not all(isinstance(value, str) for value in raw_groups):
        raise IdentityMappingError("OIDC groups claim is invalid")
    if len(raw_groups) > 200:
        raise IdentityMappingError("OIDC groups claim exceeds the JWT item limit")

    object_ids: set[str] = set()
    for value in raw_groups:
        try:
            group_id = UUID(value.strip())
        except (ValueError, AttributeError) as exc:
            raise IdentityMappingError("OIDC groups claim contains an invalid object ID") from exc
        if group_id.int == 0:
            raise IdentityMappingError("OIDC groups claim contains an invalid object ID")
        object_ids.add(str(group_id))
    return DirectoryGroupClaims(
        state=DirectoryGroupClaimState.COMPLETE,
        object_ids=frozenset(object_ids),
    )


def _has_group_overage(claims: Mapping[str, object]) -> bool:
    """Detect Entra overage markers without reading or following claim-source URLs."""
    if "hasgroups" in claims:
        if claims["hasgroups"] is not True:
            raise IdentityMappingError("OIDC hasgroups claim is invalid")
        return True

    claim_names = claims.get("_claim_names")
    if claim_names is None:
        return False
    if not isinstance(claim_names, Mapping):
        raise IdentityMappingError("OIDC distributed claim names are invalid")
    group_source = claim_names.get("groups")
    if group_source is None:
        return False
    if not isinstance(group_source, str) or not group_source.strip():
        raise IdentityMappingError("OIDC groups overage source is invalid")
    return True


def _claim_at_path(claims: Mapping[str, object], path: str) -> object:
    """Resolve a dot-separated claim path without interpreting array syntax."""
    current: object = claims
    for segment in path.split("."):
        if not segment or not isinstance(current, Mapping):
            return None
        current = current.get(segment)
    return current


def _subject_from_claims(claims: Mapping[str, object]) -> str:
    """Return the provider-neutral pairwise subject."""
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise IdentityMappingError("OIDC subject missing")
    return subject.strip()


def _directory_identity_from_claims(
    claims: Mapping[str, object],
    policy: CorporateIdentityPolicy,
) -> DirectoryIdentity:
    """Build an allowlisted corporate identity from verified Entra claims."""
    tenant_id = _uuid_claim(claims, "tid")
    if tenant_id not in policy.allowed_tenant_ids:
        raise IdentityMappingError("OIDC tenant is not allowed")
    if tenant_id != policy.issuer_tenant_id:
        raise IdentityMappingError("OIDC tenant does not match the verified issuer")
    object_id = _uuid_claim(claims, "oid")
    return DirectoryIdentity(
        tenant_id=tenant_id,
        object_id=object_id,
        account_type=_account_type(claims.get("acct")),
    )


def _uuid_claim(claims: Mapping[str, object], name: str) -> str:
    """Return a canonical non-nil UUID claim or reject the identity."""
    value = claims.get(name)
    if not isinstance(value, str):
        raise IdentityMappingError(f"OIDC {name} claim missing or invalid")
    try:
        parsed = UUID(value.strip())
    except (ValueError, AttributeError) as exc:
        raise IdentityMappingError(f"OIDC {name} claim missing or invalid") from exc
    if parsed.int == 0:
        raise IdentityMappingError(f"OIDC {name} claim missing or invalid")
    return str(parsed)


def _account_type(value: object) -> DirectoryAccountType:
    """Map the optional Entra acct claim without granting on ambiguity."""
    if not isinstance(value, bool) and (value == 0 or value == "0"):
        return DirectoryAccountType.MEMBER
    if not isinstance(value, bool) and (value == 1 or value == "1"):
        return DirectoryAccountType.GUEST
    return DirectoryAccountType.UNKNOWN


def _can_receive_approval_areas(
    account_type: DirectoryAccountType,
    policy: CorporateIdentityPolicy,
) -> bool:
    """Allow approval areas only to classified members or explicitly allowed guests."""
    if account_type is DirectoryAccountType.MEMBER:
        return True
    return account_type is DirectoryAccountType.GUEST and policy.guest_approvals_enabled

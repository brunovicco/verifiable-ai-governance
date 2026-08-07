"""Pure key lifecycle and verification policy for runtime authorization."""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

_KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


class RuntimeAuthorizationKeyStatus(StrEnum):
    """Lifecycle state for a runtime-authorization verification key."""

    ACTIVE = "active"
    RETIRING = "retiring"
    REVOKED = "revoked"


class RuntimeAuthorizationSecurityError(ValueError):
    """Base error with a stable machine-readable security code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RuntimeAuthorizationSigningError(RuntimeAuthorizationSecurityError):
    """Raised when Governance cannot emit a trusted authorization."""


class RuntimeAuthorizationVerificationError(RuntimeAuthorizationSecurityError):
    """Raised when a runtime authorization cannot be trusted."""


class RuntimeAuthorizationReplayStoreError(RuntimeAuthorizationSecurityError):
    """Raised when replay state cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class RuntimeAuthorizationVerificationKey:
    """One trusted Ed25519 public key and its verification lifecycle."""

    kid: str
    status: RuntimeAuthorizationKeyStatus
    public_jwk: str
    not_before: datetime
    verify_until: datetime

    def __post_init__(self) -> None:
        """Reject malformed identifiers, windows, and public-key documents."""
        if not _KEY_ID_RE.fullmatch(self.kid):
            raise ValueError("Runtime authorization kid is invalid")
        _require_utc(self.not_before, "key not_before")
        _require_utc(self.verify_until, "key verify_until")
        if self.verify_until <= self.not_before:
            raise ValueError("Runtime authorization key window is invalid")
        if len(self.public_jwk.encode("utf-8")) > 8192:
            raise ValueError("Runtime authorization public JWK is too large")
        try:
            jwk = json.loads(self.public_jwk)
        except json.JSONDecodeError as exc:
            raise ValueError("Runtime authorization public JWK must be valid JSON") from exc
        if not isinstance(jwk, dict):
            raise ValueError("Runtime authorization public JWK must be a JSON object")
        if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
            raise ValueError("Runtime authorization key must be an Ed25519 OKP JWK")
        if jwk.get("kid") not in {None, self.kid}:
            raise ValueError("Runtime authorization JWK kid does not match key metadata")
        x = jwk.get("x")
        if not isinstance(x, str) or not x:
            raise ValueError("Runtime authorization JWK must include public coordinate x")

    @property
    def verification_enabled(self) -> bool:
        """Return whether the lifecycle permits signature verification."""
        return self.status in {
            RuntimeAuthorizationKeyStatus.ACTIVE,
            RuntimeAuthorizationKeyStatus.RETIRING,
        }

    @property
    def signing_enabled(self) -> bool:
        """Return whether Governance may emit new artifacts with this key."""
        return self.status is RuntimeAuthorizationKeyStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class RuntimeAuthorizationKeySet:
    """Versioned trusted key set used by authorization consumers."""

    generation: int
    keys: tuple[RuntimeAuthorizationVerificationKey, ...]

    def __post_init__(self) -> None:
        """Require a non-empty, uniquely identified key set with an active key."""
        if self.generation < 1:
            raise ValueError("Runtime authorization key-set generation must be positive")
        if not self.keys:
            raise ValueError("Runtime authorization key set must not be empty")
        kids = [key.kid for key in self.keys]
        if len(kids) != len(set(kids)):
            raise ValueError("Runtime authorization key set contains duplicate kids")
        if not any(key.signing_enabled for key in self.keys):
            raise ValueError("Runtime authorization key set requires at least one active key")

    def resolve(self, kid: str) -> RuntimeAuthorizationVerificationKey | None:
        """Resolve one exact key identifier without fallback."""
        return next((key for key in self.keys if key.kid == kid), None)


@dataclass(frozen=True, slots=True)
class RuntimeAuthorizationSigningKey:
    """Private signing material supplied by a secret manager or secure runtime."""

    kid: str
    private_key_pem: str

    def __post_init__(self) -> None:
        """Require bounded non-empty signing material without logging it."""
        if not _KEY_ID_RE.fullmatch(self.kid):
            raise ValueError("Runtime authorization signing kid is invalid")
        encoded = self.private_key_pem.encode("utf-8")
        if not encoded or len(encoded) > 16384:
            raise ValueError("Runtime authorization private key is invalid")


@dataclass(frozen=True, slots=True)
class RuntimeAuthorizationVerificationPolicy:
    """Consumer-specific trust boundary for runtime authorization."""

    issuer: str
    audience: str
    clock_skew_seconds: int = 0

    def __post_init__(self) -> None:
        """Reject ambiguous issuer, audience, or excessive clock skew."""
        if not _KEY_ID_RE.fullmatch(self.issuer):
            raise ValueError("Runtime authorization issuer is invalid")
        if not _KEY_ID_RE.fullmatch(self.audience):
            raise ValueError("Runtime authorization audience is invalid")
        if not 0 <= self.clock_skew_seconds <= 60:
            raise ValueError("Runtime authorization clock skew must be between 0 and 60 seconds")


def load_runtime_authorization_key_set_json(raw_json: str) -> RuntimeAuthorizationKeySet:
    """Load one strict public key-set document from JSON."""
    try:
        document = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Runtime authorization key set must be valid JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("Runtime authorization key set must be a JSON object")
    allowed_document_fields = {"schema_version", "generation", "keys"}
    if set(document) != allowed_document_fields:
        raise ValueError("Runtime authorization key set contains unsupported fields")
    if document.get("schema_version") != "1.0":
        raise ValueError("Unsupported runtime authorization key-set schema version")
    generation = document.get("generation")
    raw_keys = document.get("keys")
    if not isinstance(generation, int) or isinstance(generation, bool):
        raise ValueError("Runtime authorization key-set generation must be an integer")
    if not isinstance(raw_keys, list):
        raise ValueError("Runtime authorization key-set keys must be an array")

    keys: list[RuntimeAuthorizationVerificationKey] = []
    for item in raw_keys:
        if not isinstance(item, dict):
            raise ValueError("Runtime authorization key entry must be an object")
        allowed_key_fields = {
            "kid",
            "status",
            "not_before",
            "verify_until",
            "jwk",
        }
        if set(item) != allowed_key_fields:
            raise ValueError("Runtime authorization key entry contains unsupported fields")
        kid = item.get("kid")
        status = item.get("status")
        not_before = item.get("not_before")
        verify_until = item.get("verify_until")
        jwk = item.get("jwk")
        if not isinstance(kid, str) or not isinstance(status, str):
            raise ValueError("Runtime authorization key id and status must be strings")
        if not isinstance(not_before, str) or not isinstance(verify_until, str):
            raise ValueError("Runtime authorization key timestamps must be strings")
        if not isinstance(jwk, dict):
            raise ValueError("Runtime authorization jwk must be an object")
        try:
            key_status = RuntimeAuthorizationKeyStatus(status)
        except ValueError as exc:
            raise ValueError("Runtime authorization key status is invalid") from exc
        key = RuntimeAuthorizationVerificationKey(
            kid=kid,
            status=key_status,
            public_jwk=json.dumps(
                {**jwk, "kid": kid},
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            not_before=_parse_utc(not_before, "key not_before"),
            verify_until=_parse_utc(verify_until, "key verify_until"),
        )
        keys.append(key)

    return RuntimeAuthorizationKeySet(generation=generation, keys=tuple(keys))


def runtime_authorization_key_set_json(key_set: RuntimeAuthorizationKeySet) -> str:
    """Serialize a trusted public key set without private material."""
    document: dict[str, Any] = {
        "schema_version": "1.0",
        "generation": key_set.generation,
        "keys": [
            {
                "kid": key.kid,
                "status": key.status.value,
                "not_before": _utc_text(key.not_before),
                "verify_until": _utc_text(key.verify_until),
                "jwk": {
                    name: value
                    for name, value in json.loads(key.public_jwk).items()
                    if name != "kid"
                },
            }
            for key in sorted(key_set.keys, key=lambda item: item.kid)
        ],
    }
    return json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _parse_utc(value: str, label: str) -> datetime:
    """Parse one ISO-8601 UTC timestamp."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    _require_utc(parsed, label)
    return parsed.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    """Serialize UTC using the interoperable Z suffix."""
    _require_utc(value, "timestamp")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _require_utc(value: datetime, label: str) -> None:
    """Require explicit UTC rather than silently normalizing trust timestamps."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be expressed in UTC")

"""Issue and verify signed runtime authorization artifacts."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from governance_schemas.runtime_authorization import (
    RuntimeAuthorizationClaims,
    RuntimeAuthorizationProtectedHeader,
    SignedRuntimeAuthorization,
    canonical_json_bytes,
)

from ai_governance_api.domain.runtime_authorization_security import (
    RuntimeAuthorizationKeySet,
    RuntimeAuthorizationReplayStoreError,
    RuntimeAuthorizationSecurityError,
    RuntimeAuthorizationSigningError,
    RuntimeAuthorizationSigningKey,
    RuntimeAuthorizationVerificationError,
    RuntimeAuthorizationVerificationPolicy,
)


class RuntimeAuthorizationSignatureProvider(Protocol):
    """Port for signing and verifying the P1.1 canonical byte sequence."""

    def sign(self, payload: bytes, private_key_pem: str) -> str:
        """Return an unpadded Ed25519 signature."""

    def verify(self, payload: bytes, public_jwk: str, signature: str) -> bool:
        """Return whether one signature is valid for the supplied public key."""


class RuntimeAuthorizationReplayGuard(Protocol):
    """Port for single-use authorization ID consumption."""

    def consume(
        self,
        authorization_id: UUID,
        *,
        expires_at: datetime,
        now: datetime,
    ) -> bool:
        """Atomically return whether this authorization ID was newly consumed."""


@dataclass(frozen=True, slots=True)
class VerifiedRuntimeAuthorization:
    """Trusted authorization result safe for downstream policy enforcement."""

    envelope: SignedRuntimeAuthorization
    verified_at: datetime
    kid: str
    key_set_generation: int
    signing_digest: str


class RuntimeAuthorizationSigner:
    """Emit Ed25519-signed runtime authorizations with one active key."""

    _PAIR_CHECK_PAYLOAD = b"verifiable-ai-governance/runtime-authorization/key-check/v1"

    def __init__(
        self,
        signing_key: RuntimeAuthorizationSigningKey,
        key_set: RuntimeAuthorizationKeySet,
        signature_provider: RuntimeAuthorizationSignatureProvider,
        *,
        issuer: str,
    ) -> None:
        """Bind a private key to one active public key and trusted issuer."""
        self._signing_key = signing_key
        self._key_set = key_set
        self._signature_provider = signature_provider
        self._issuer = issuer

        verification_key = key_set.resolve(signing_key.kid)
        if verification_key is None:
            raise RuntimeAuthorizationSigningError(
                "unknown_signing_key",
                "Signing key is absent from the trusted runtime authorization key set",
            )
        if not verification_key.signing_enabled:
            raise RuntimeAuthorizationSigningError(
                "signing_key_not_active",
                "Only an active runtime authorization key may sign new artifacts",
            )

        try:
            challenge_signature = signature_provider.sign(
                self._PAIR_CHECK_PAYLOAD,
                signing_key.private_key_pem,
            )
        except RuntimeAuthorizationSecurityError as exc:
            raise RuntimeAuthorizationSigningError(exc.code, str(exc)) from exc
        if not signature_provider.verify(
            self._PAIR_CHECK_PAYLOAD,
            verification_key.public_jwk,
            challenge_signature,
        ):
            raise RuntimeAuthorizationSigningError(
                "signing_key_mismatch",
                "Runtime authorization private key does not match trusted public key",
            )

    def sign(self, claims: RuntimeAuthorizationClaims) -> SignedRuntimeAuthorization:
        """Sign validated claims and return one complete bearer-like envelope."""
        if claims.issuer != self._issuer:
            raise RuntimeAuthorizationSigningError(
                "issuer_mismatch",
                "Runtime authorization claims issuer does not match configured signer",
            )
        verification_key = self._key_set.resolve(self._signing_key.kid)
        if verification_key is None or not verification_key.signing_enabled:
            raise RuntimeAuthorizationSigningError(
                "signing_key_not_active",
                "Runtime authorization signing key is no longer active",
            )
        if not (verification_key.not_before <= claims.issued_at < verification_key.verify_until):
            raise RuntimeAuthorizationSigningError(
                "signing_key_outside_window",
                "Runtime authorization signing key is outside its validity window",
            )

        protected = RuntimeAuthorizationProtectedHeader(kid=self._signing_key.kid)
        payload = runtime_authorization_signing_bytes(protected, claims)
        try:
            signature = self._signature_provider.sign(
                payload,
                self._signing_key.private_key_pem,
            )
        except RuntimeAuthorizationSecurityError as exc:
            raise RuntimeAuthorizationSigningError(exc.code, str(exc)) from exc
        return SignedRuntimeAuthorization(
            protected=protected,
            claims=claims,
            signature=signature,
        )


class RuntimeAuthorizationVerifier:
    """Fail-closed verifier for signature, trust boundary, time, key, and replay."""

    def __init__(
        self,
        key_set: RuntimeAuthorizationKeySet,
        signature_provider: RuntimeAuthorizationSignatureProvider,
        replay_guard: RuntimeAuthorizationReplayGuard,
        policy: RuntimeAuthorizationVerificationPolicy,
    ) -> None:
        """Create a verifier that requires replay protection for every success."""
        self._key_set = key_set
        self._signature_provider = signature_provider
        self._replay_guard = replay_guard
        self._policy = policy

    def verify(
        self,
        envelope: SignedRuntimeAuthorization,
        *,
        now: datetime,
    ) -> VerifiedRuntimeAuthorization:
        """Verify one authorization and atomically consume its replay identifier."""
        _require_utc(now, "verification time")
        claims = envelope.claims
        skew = timedelta(seconds=self._policy.clock_skew_seconds)

        if claims.issuer != self._policy.issuer:
            raise RuntimeAuthorizationVerificationError(
                "issuer_mismatch",
                "Runtime authorization issuer is not trusted by this consumer",
            )
        if self._policy.audience not in claims.audience:
            raise RuntimeAuthorizationVerificationError(
                "audience_mismatch",
                "Runtime authorization audience does not include this consumer",
            )
        if claims.issued_at > now + skew:
            raise RuntimeAuthorizationVerificationError(
                "issued_in_future",
                "Runtime authorization was issued in the future",
            )
        if claims.not_before > now + skew:
            raise RuntimeAuthorizationVerificationError(
                "not_yet_valid",
                "Runtime authorization is not valid yet",
            )
        if claims.expires_at <= now - skew:
            raise RuntimeAuthorizationVerificationError(
                "expired",
                "Runtime authorization has expired",
            )

        key = self._key_set.resolve(envelope.protected.kid)
        if key is None:
            raise RuntimeAuthorizationVerificationError(
                "unknown_key",
                "Runtime authorization key identifier is not trusted",
            )
        if not key.verification_enabled:
            raise RuntimeAuthorizationVerificationError(
                "key_revoked",
                "Runtime authorization key has been revoked",
            )
        if not (key.not_before <= claims.issued_at < key.verify_until):
            raise RuntimeAuthorizationVerificationError(
                "key_not_valid_for_issue_time",
                "Runtime authorization was issued outside the trusted key window",
            )
        if now - skew >= key.verify_until:
            raise RuntimeAuthorizationVerificationError(
                "key_verification_window_closed",
                "Runtime authorization key verification window has closed",
            )

        payload = runtime_authorization_signing_bytes(envelope.protected, claims)
        if not self._signature_provider.verify(
            payload,
            key.public_jwk,
            envelope.signature,
        ):
            raise RuntimeAuthorizationVerificationError(
                "invalid_signature",
                "Runtime authorization signature is invalid",
            )

        try:
            fresh = self._replay_guard.consume(
                claims.authorization_id,
                expires_at=claims.expires_at,
                now=now,
            )
        except RuntimeAuthorizationReplayStoreError as exc:
            raise RuntimeAuthorizationVerificationError(
                exc.code,
                str(exc),
            ) from exc
        except Exception as exc:
            raise RuntimeAuthorizationVerificationError(
                "replay_store_unavailable",
                "Runtime authorization replay state is unavailable",
            ) from exc
        if not fresh:
            raise RuntimeAuthorizationVerificationError(
                "replay_detected",
                "Runtime authorization identifier was already consumed",
            )

        return VerifiedRuntimeAuthorization(
            envelope=envelope,
            verified_at=now,
            kid=key.kid,
            key_set_generation=self._key_set.generation,
            signing_digest=hashlib.sha256(payload).hexdigest(),
        )


def runtime_authorization_signing_bytes(
    protected: RuntimeAuthorizationProtectedHeader,
    claims: RuntimeAuthorizationClaims,
) -> bytes:
    """Return the exact P1.1 bytes covered by the Ed25519 signature."""
    return canonical_json_bytes(
        {
            "protected": protected.model_dump(mode="json"),
            "claims": claims.model_dump(mode="json"),
        }
    )


def _require_utc(value: datetime, label: str) -> None:
    """Require explicit UTC for verification decisions."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeAuthorizationVerificationError(
            "invalid_time",
            f"{label} must be timezone-aware",
        )
    if value.utcoffset() != UTC.utcoffset(value):
        raise RuntimeAuthorizationVerificationError(
            "invalid_time",
            f"{label} must be expressed in UTC",
        )

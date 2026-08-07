"""End-to-end tests for P1.2 Ed25519 runtime authorization trust."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from ai_governance_api.adapters.runtime_authorization_crypto import (
    PyJwtEd25519SignatureProvider,
)
from ai_governance_api.adapters.runtime_authorization_replay import (
    InMemoryRuntimeAuthorizationReplayGuard,
)
from ai_governance_api.application.runtime_authorization_security import (
    RuntimeAuthorizationSigner,
    RuntimeAuthorizationVerifier,
    runtime_authorization_signing_bytes,
)
from ai_governance_api.domain.runtime_authorization_security import (
    RuntimeAuthorizationKeySet,
    RuntimeAuthorizationKeyStatus,
    RuntimeAuthorizationSigningError,
    RuntimeAuthorizationSigningKey,
    RuntimeAuthorizationVerificationError,
    RuntimeAuthorizationVerificationKey,
    RuntimeAuthorizationVerificationPolicy,
    load_runtime_authorization_key_set_json,
    runtime_authorization_key_set_json,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from governance_schemas.enums import (
    AutonomyLevel,
    DataClassification,
    RiskTier,
)
from governance_schemas.runtime_authorization import (
    AuthorizedRuntimeModel,
    RuntimeAuthorizationClaims,
    RuntimeAuthorizationPolicyProvenance,
    RuntimeAuthorizationScope,
    RuntimeAuthorizationSubject,
    RuntimeRequestBinding,
    SignedRuntimeAuthorization,
)
from jwt.algorithms import get_default_algorithms

NOW = datetime(2026, 8, 7, 15, 30, tzinfo=UTC)
ISSUER = "verifiable-ai-governance:production"
AUDIENCE = "policy-model-router"


def _key_material(
    kid: str,
    *,
    status: RuntimeAuthorizationKeyStatus = RuntimeAuthorizationKeyStatus.ACTIVE,
    private_key: Ed25519PrivateKey | None = None,
) -> tuple[RuntimeAuthorizationSigningKey, RuntimeAuthorizationVerificationKey]:
    """Generate one ephemeral test-only Ed25519 key pair."""
    private = private_key or Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    public = private.public_key()
    jwk = json.loads(get_default_algorithms()["EdDSA"].to_jwk(public))
    jwk["kid"] = kid
    verification = RuntimeAuthorizationVerificationKey(
        kid=kid,
        status=status,
        public_jwk=json.dumps(jwk, separators=(",", ":"), sort_keys=True),
        not_before=NOW - timedelta(days=1),
        verify_until=NOW + timedelta(days=1),
    )
    return RuntimeAuthorizationSigningKey(kid=kid, private_key_pem=private_pem), verification


def _claims(**overrides: object) -> RuntimeAuthorizationClaims:
    """Return one synthetic short-lived credit authorization."""
    values: dict[str, object] = {
        "authorization_id": "55555555-5555-4555-8555-555555555555",
        "issuer": ISSUER,
        "audience": ("multi-agent-credit-desk", AUDIENCE),
        "issued_at": NOW,
        "not_before": NOW,
        "expires_at": NOW + timedelta(minutes=5),
        "subject": RuntimeAuthorizationSubject(
            initiative_id="11111111-1111-4111-8111-111111111111",
            ai_system_id="22222222-2222-4222-8222-222222222222",
            ai_system_version=4,
            agent_id="33333333-3333-4333-8333-333333333333",
            agent_version=7,
            agent_review_digest="b" * 64,
        ),
        "request": RuntimeRequestBinding(
            workflow_id="credit-analysis-2026-001",
            task_id="draft-opinion",
            workload="opinion_drafting",
            context_tokens_estimated=3000,
            max_output_tokens_estimated=900,
            structured_output_required=True,
            max_latency_ms=4500,
            max_cost_usd_micros=300_000,
        ),
        "scope": RuntimeAuthorizationScope(
            risk_tier=RiskTier.HIGH,
            data_classification=DataClassification.RESTRICTED,
            autonomy_level=AutonomyLevel.A2_PREPARE_FOR_APPROVAL,
            models=(
                AuthorizedRuntimeModel(
                    model_id="44444444-4444-4444-8444-444444444444",
                    entity_version=2,
                    model_version="2026.08.0",
                    routing_group="credit-opinion-approved",
                    review_digest="a" * 64,
                    allowed_data_classes=(DataClassification.RESTRICTED,),
                ),
            ),
            allowed_tools=(
                "bureau-mcp:read",
                "credit-core:read",
                "policy-mcp:read",
            ),
            permissions=(
                "credit:analysis:read",
                "credit:opinion:draft",
            ),
            max_runtime_seconds=30,
            human_approval_points=("final-credit-approval",),
            kill_switch_enabled=True,
        ),
        "scope_digest": "c" * 64,
        "policy": RuntimeAuthorizationPolicyProvenance(
            policy_id="baseline-governance-policy",
            policy_version="1.0.0",
            policy_digest="d" * 64,
            control_catalog_id="verifiable-ai-governance-baseline",
            control_catalog_version="1.0.0",
            control_catalog_digest="e" * 64,
        ),
    }
    values.update(overrides)
    return RuntimeAuthorizationClaims(**values)


def _verifier(
    key_set: RuntimeAuthorizationKeySet,
    *,
    audience: str = AUDIENCE,
    replay_max_entries: int = 100,
) -> RuntimeAuthorizationVerifier:
    """Create one consumer verifier with mandatory replay protection."""
    return RuntimeAuthorizationVerifier(
        key_set,
        PyJwtEd25519SignatureProvider(),
        InMemoryRuntimeAuthorizationReplayGuard(max_entries=replay_max_entries),
        RuntimeAuthorizationVerificationPolicy(
            issuer=ISSUER,
            audience=audience,
        ),
    )


def test_sign_and_verify_ed25519_authorization() -> None:
    signing_key, verification_key = _key_material("gov-ed25519-2026-01")
    key_set = RuntimeAuthorizationKeySet(1, (verification_key,))
    signer = RuntimeAuthorizationSigner(
        signing_key,
        key_set,
        PyJwtEd25519SignatureProvider(),
        issuer=ISSUER,
    )
    envelope = signer.sign(_claims())

    verified = _verifier(key_set).verify(envelope, now=NOW + timedelta(seconds=1))

    assert verified.envelope == envelope
    assert verified.kid == "gov-ed25519-2026-01"
    assert verified.key_set_generation == 1
    assert len(verified.signing_digest) == 64
    assert envelope.signing_bytes() == runtime_authorization_signing_bytes(
        envelope.protected,
        envelope.claims,
    )


def test_ed25519_signature_is_deterministic_for_same_bytes() -> None:
    signing_key, verification_key = _key_material("gov-ed25519-2026-01")
    key_set = RuntimeAuthorizationKeySet(1, (verification_key,))
    signer = RuntimeAuthorizationSigner(
        signing_key,
        key_set,
        PyJwtEd25519SignatureProvider(),
        issuer=ISSUER,
    )

    first = signer.sign(_claims())
    second = signer.sign(_claims())

    assert first.signature == second.signature
    assert first.signing_digest() == second.signing_digest()


def test_tampered_claims_fail_signature_verification() -> None:
    signing_key, verification_key = _key_material("gov-ed25519-2026-01")
    key_set = RuntimeAuthorizationKeySet(1, (verification_key,))
    signer = RuntimeAuthorizationSigner(
        signing_key,
        key_set,
        PyJwtEd25519SignatureProvider(),
        issuer=ISSUER,
    )
    original = signer.sign(_claims())
    tampered = SignedRuntimeAuthorization(
        protected=original.protected,
        claims=original.claims.model_copy(
            update={"scope_digest": "f" * 64},
        ),
        signature=original.signature,
    )

    with pytest.raises(RuntimeAuthorizationVerificationError) as exc_info:
        _verifier(key_set).verify(tampered, now=NOW + timedelta(seconds=1))

    assert exc_info.value.code == "invalid_signature"


def test_unknown_and_revoked_keys_fail_closed() -> None:
    signing_key, verification_key = _key_material("gov-ed25519-old")
    signer_set = RuntimeAuthorizationKeySet(1, (verification_key,))
    envelope = RuntimeAuthorizationSigner(
        signing_key,
        signer_set,
        PyJwtEd25519SignatureProvider(),
        issuer=ISSUER,
    ).sign(_claims())

    _, other_key = _key_material("gov-ed25519-other")
    with pytest.raises(RuntimeAuthorizationVerificationError) as unknown:
        _verifier(RuntimeAuthorizationKeySet(2, (other_key,))).verify(
            envelope,
            now=NOW + timedelta(seconds=1),
        )
    assert unknown.value.code == "unknown_key"

    revoked = RuntimeAuthorizationVerificationKey(
        kid=verification_key.kid,
        status=RuntimeAuthorizationKeyStatus.REVOKED,
        public_jwk=verification_key.public_jwk,
        not_before=verification_key.not_before,
        verify_until=verification_key.verify_until,
    )
    _, active_other = _key_material("gov-ed25519-active")
    revoked_set = RuntimeAuthorizationKeySet(3, (revoked, active_other))
    with pytest.raises(RuntimeAuthorizationVerificationError) as revoked_error:
        _verifier(revoked_set).verify(
            envelope,
            now=NOW + timedelta(seconds=1),
        )
    assert revoked_error.value.code == "key_revoked"


def test_rotation_accepts_retiring_key_but_forbids_new_signatures() -> None:
    old_signing, old_active = _key_material("gov-ed25519-2026-01")
    old_set = RuntimeAuthorizationKeySet(1, (old_active,))
    old_envelope = RuntimeAuthorizationSigner(
        old_signing,
        old_set,
        PyJwtEd25519SignatureProvider(),
        issuer=ISSUER,
    ).sign(_claims())

    new_signing, new_active = _key_material("gov-ed25519-2026-02")
    old_retiring = RuntimeAuthorizationVerificationKey(
        kid=old_active.kid,
        status=RuntimeAuthorizationKeyStatus.RETIRING,
        public_jwk=old_active.public_jwk,
        not_before=old_active.not_before,
        verify_until=old_active.verify_until,
    )
    rotated_set = RuntimeAuthorizationKeySet(
        2,
        (old_retiring, new_active),
    )

    verified_old = _verifier(rotated_set).verify(
        old_envelope,
        now=NOW + timedelta(seconds=1),
    )
    assert verified_old.kid == old_retiring.kid

    with pytest.raises(RuntimeAuthorizationSigningError) as old_sign_error:
        RuntimeAuthorizationSigner(
            old_signing,
            rotated_set,
            PyJwtEd25519SignatureProvider(),
            issuer=ISSUER,
        )
    assert old_sign_error.value.code == "signing_key_not_active"

    new_envelope = RuntimeAuthorizationSigner(
        new_signing,
        rotated_set,
        PyJwtEd25519SignatureProvider(),
        issuer=ISSUER,
    ).sign(_claims(authorization_id="66666666-6666-4666-8666-666666666666"))
    verified_new = _verifier(rotated_set).verify(
        new_envelope,
        now=NOW + timedelta(seconds=1),
    )
    assert verified_new.kid == new_active.kid


def test_signer_rejects_private_public_key_mismatch() -> None:
    signing_key, _ = _key_material("gov-ed25519-2026-01")
    _, unrelated_public = _key_material("gov-ed25519-2026-01")
    key_set = RuntimeAuthorizationKeySet(1, (unrelated_public,))

    with pytest.raises(RuntimeAuthorizationSigningError) as exc_info:
        RuntimeAuthorizationSigner(
            signing_key,
            key_set,
            PyJwtEd25519SignatureProvider(),
            issuer=ISSUER,
        )

    assert exc_info.value.code == "signing_key_mismatch"


@pytest.mark.parametrize(
    ("claims", "now", "expected_code"),
    [
        (
            _claims(issuer="untrusted-issuer"),
            NOW + timedelta(seconds=1),
            "issuer_mismatch",
        ),
        (
            _claims(audience=("multi-agent-credit-desk",)),
            NOW + timedelta(seconds=1),
            "audience_mismatch",
        ),
        (
            _claims(
                issued_at=NOW + timedelta(seconds=20),
                not_before=NOW + timedelta(seconds=20),
                expires_at=NOW + timedelta(minutes=5),
            ),
            NOW,
            "issued_in_future",
        ),
        (
            _claims(),
            NOW + timedelta(minutes=6),
            "expired",
        ),
    ],
)
def test_consumer_trust_boundary_rejects_invalid_context(
    claims: RuntimeAuthorizationClaims,
    now: datetime,
    expected_code: str,
) -> None:
    signing_key, verification_key = _key_material("gov-ed25519-2026-01")
    key_set = RuntimeAuthorizationKeySet(1, (verification_key,))
    signer = RuntimeAuthorizationSigner(
        signing_key,
        key_set,
        PyJwtEd25519SignatureProvider(),
        issuer=claims.issuer,
    )
    envelope = signer.sign(claims)

    verifier = _verifier(key_set)
    with pytest.raises(RuntimeAuthorizationVerificationError) as exc_info:
        verifier.verify(envelope, now=now)

    assert exc_info.value.code == expected_code


def test_replay_is_rejected_after_first_success() -> None:
    signing_key, verification_key = _key_material("gov-ed25519-2026-01")
    key_set = RuntimeAuthorizationKeySet(1, (verification_key,))
    envelope = RuntimeAuthorizationSigner(
        signing_key,
        key_set,
        PyJwtEd25519SignatureProvider(),
        issuer=ISSUER,
    ).sign(_claims())
    verifier = _verifier(key_set)

    verifier.verify(envelope, now=NOW + timedelta(seconds=1))
    with pytest.raises(RuntimeAuthorizationVerificationError) as replay:
        verifier.verify(envelope, now=NOW + timedelta(seconds=2))

    assert replay.value.code == "replay_detected"


def test_replay_store_capacity_fails_closed() -> None:
    signing_key, verification_key = _key_material("gov-ed25519-2026-01")
    key_set = RuntimeAuthorizationKeySet(1, (verification_key,))
    signer = RuntimeAuthorizationSigner(
        signing_key,
        key_set,
        PyJwtEd25519SignatureProvider(),
        issuer=ISSUER,
    )
    verifier = _verifier(key_set, replay_max_entries=1)

    verifier.verify(
        signer.sign(_claims()),
        now=NOW + timedelta(seconds=1),
    )
    second = signer.sign(_claims(authorization_id="77777777-7777-4777-8777-777777777777"))
    with pytest.raises(RuntimeAuthorizationVerificationError) as capacity:
        verifier.verify(second, now=NOW + timedelta(seconds=2))

    assert capacity.value.code == "replay_store_full"


def test_public_key_set_json_round_trip_is_canonical() -> None:
    _, first = _key_material("gov-ed25519-2026-01")
    _, second = _key_material(
        "gov-ed25519-2026-00",
        status=RuntimeAuthorizationKeyStatus.RETIRING,
    )
    key_set = RuntimeAuthorizationKeySet(7, (first, second))

    encoded = runtime_authorization_key_set_json(key_set)
    decoded = load_runtime_authorization_key_set_json(encoded)

    assert decoded == RuntimeAuthorizationKeySet(7, (second, first))
    assert runtime_authorization_key_set_json(decoded) == encoded
    assert "PRIVATE KEY" not in encoded

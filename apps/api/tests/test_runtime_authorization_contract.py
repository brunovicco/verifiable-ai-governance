from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from governance_schemas import (
    AutonomyLevel,
    DataClassification,
    RiskTier,
)
from governance_schemas.runtime_authorization import (
    MAX_AUTHORIZATION_LIFETIME_SECONDS,
    AuthorizedRuntimeModel,
    RuntimeAuthorizationClaims,
    RuntimeAuthorizationPolicyProvenance,
    RuntimeAuthorizationProtectedHeader,
    RuntimeAuthorizationScope,
    RuntimeAuthorizationSubject,
    RuntimeRequestBinding,
    SignedRuntimeAuthorization,
)
from pydantic import ValidationError

NOW = datetime(2026, 8, 7, 13, 30, tzinfo=UTC)
INITIATIVE_ID = UUID("11111111-1111-4111-8111-111111111111")
SYSTEM_ID = UUID("22222222-2222-4222-8222-222222222222")
AGENT_ID = UUID("33333333-3333-4333-8333-333333333333")
MODEL_ID = UUID("44444444-4444-4444-8444-444444444444")


def envelope(**claim_overrides: object) -> SignedRuntimeAuthorization:
    """Return one deterministic, syntactically signed authorization fixture."""
    model = AuthorizedRuntimeModel(
        model_id=MODEL_ID,
        entity_version=2,
        model_version="2026.08.0",
        routing_group="credit-opinion-approved",
        review_digest="a" * 64,
        allowed_data_classes=(DataClassification.RESTRICTED,),
    )
    values: dict[str, object] = {
        "schema_version": "1.0",
        "authorization_id": UUID("55555555-5555-4555-8555-555555555555"),
        "issuer": "verifiable-ai-governance:production",
        "audience": ("multi-agent-credit-desk", "policy-model-router"),
        "issued_at": NOW,
        "not_before": NOW,
        "expires_at": NOW + timedelta(minutes=5),
        "subject": RuntimeAuthorizationSubject(
            initiative_id=INITIATIVE_ID,
            ai_system_id=SYSTEM_ID,
            ai_system_version=4,
            agent_id=AGENT_ID,
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
            models=(model,),
            allowed_tools=(
                "credit-core:read",
                "policy-mcp:read",
                "bureau-mcp:read",
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
    values.update(claim_overrides)
    return SignedRuntimeAuthorization(
        protected=RuntimeAuthorizationProtectedHeader(kid="gov-ed25519-2026-01"),
        claims=RuntimeAuthorizationClaims(**values),
        signature="A" * 86,
    )


def test_signing_bytes_are_stable_for_set_like_ordering() -> None:
    first = envelope()
    scope = first.claims.scope
    reordered = envelope(
        audience=("policy-model-router", "multi-agent-credit-desk"),
        scope=RuntimeAuthorizationScope(
            risk_tier=scope.risk_tier,
            data_classification=scope.data_classification,
            autonomy_level=scope.autonomy_level,
            models=scope.models,
            allowed_tools=tuple(reversed(scope.allowed_tools)),
            permissions=tuple(reversed(scope.permissions)),
            max_runtime_seconds=scope.max_runtime_seconds,
            human_approval_points=scope.human_approval_points,
            kill_switch_enabled=True,
        ),
    )

    assert first.signing_bytes() == reordered.signing_bytes()
    assert first.signing_digest() == reordered.signing_digest()


def test_protected_key_id_is_covered_by_signing_bytes() -> None:
    first = envelope()
    changed = SignedRuntimeAuthorization(
        protected=RuntimeAuthorizationProtectedHeader(kid="gov-ed25519-2026-02"),
        claims=first.claims,
        signature=first.signature,
    )

    assert first.signing_bytes() != changed.signing_bytes()
    assert first.signing_digest() != changed.signing_digest()


def test_request_binding_prevents_cross_task_replay() -> None:
    first = envelope()
    changed_request = first.claims.request.model_copy(update={"task_id": "approve-credit"})
    changed = envelope(request=changed_request)

    assert first.signing_digest() != changed.signing_digest()


def test_contract_rejects_overlong_authorization_lifetime() -> None:
    with pytest.raises(ValidationError, match="lifetime exceeds"):
        envelope(expires_at=NOW + timedelta(seconds=MAX_AUTHORIZATION_LIFETIME_SECONDS + 1))


def test_contract_rejects_non_utc_timestamps() -> None:
    local_time = NOW.astimezone().replace(tzinfo=None)

    with pytest.raises(ValidationError, match="timezone-aware"):
        envelope(issued_at=local_time)


def test_contract_requires_model_compatible_with_data_classification() -> None:
    model = AuthorizedRuntimeModel(
        model_id=MODEL_ID,
        entity_version=2,
        model_version="2026.08.0",
        routing_group="credit-opinion-approved",
        review_digest="a" * 64,
        allowed_data_classes=(DataClassification.INTERNAL,),
    )

    with pytest.raises(ValidationError, match="allow the runtime data class"):
        RuntimeAuthorizationScope(
            risk_tier=RiskTier.HIGH,
            data_classification=DataClassification.RESTRICTED,
            autonomy_level=AutonomyLevel.A2_PREPARE_FOR_APPROVAL,
            models=(model,),
            max_runtime_seconds=30,
            human_approval_points=("final-credit-approval",),
            kill_switch_enabled=True,
        )


def test_contract_requires_permission_boundary_for_tools() -> None:
    current = envelope().claims.scope

    with pytest.raises(ValidationError, match="permission boundary"):
        RuntimeAuthorizationScope(
            risk_tier=current.risk_tier,
            data_classification=current.data_classification,
            autonomy_level=current.autonomy_level,
            models=current.models,
            allowed_tools=("credit-core:read",),
            permissions=(),
            max_runtime_seconds=30,
            human_approval_points=current.human_approval_points,
            kill_switch_enabled=True,
        )


def test_signature_is_syntactically_ed25519_sized() -> None:
    current = envelope()

    with pytest.raises(ValidationError):
        SignedRuntimeAuthorization(
            protected=current.protected,
            claims=current.claims,
            signature="too-short",
        )

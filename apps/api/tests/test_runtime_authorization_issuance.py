"""Tests for P1.3 Governance runtime authorization issuance."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from ai_governance_api.adapters.runtime_authorization_crypto import (
    PyJwtEd25519SignatureProvider,
)
from ai_governance_api.application.runtime_authorization_issuance import (
    GovernanceRuntimeAuthorizationIssuer,
    RuntimeAuthorizationIssuanceError,
    RuntimeAuthorizationIssuancePolicy,
)
from ai_governance_api.application.runtime_authorization_security import (
    RuntimeAuthorizationSigner,
)
from ai_governance_api.domain.model_routing import (
    GovernedRoutingModel,
    GovernedRoutingScope,
    ModelRoutingCommand,
    RoutingWorkload,
)
from ai_governance_api.domain.runtime_authorization_security import (
    RuntimeAuthorizationKeySet,
    RuntimeAuthorizationKeyStatus,
    RuntimeAuthorizationSigningKey,
    RuntimeAuthorizationVerificationKey,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from governance_schemas import (
    AutonomyLevel,
    DataClassification,
    EntityStatus,
    RiskTier,
)
from jwt.algorithms import get_default_algorithms

NOW = datetime(2026, 8, 7, 18, 0, tzinfo=UTC)


def _signer() -> RuntimeAuthorizationSigner:
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    public_jwk = json.loads(get_default_algorithms()["EdDSA"].to_jwk(private.public_key()))
    public_jwk["kid"] = "gov-ed25519-p13-test"
    verification = RuntimeAuthorizationVerificationKey(
        kid="gov-ed25519-p13-test",
        status=RuntimeAuthorizationKeyStatus.ACTIVE,
        public_jwk=json.dumps(public_jwk, separators=(",", ":"), sort_keys=True),
        not_before=NOW - timedelta(days=1),
        verify_until=NOW + timedelta(days=1),
    )
    return RuntimeAuthorizationSigner(
        RuntimeAuthorizationSigningKey(
            kid="gov-ed25519-p13-test",
            private_key_pem=private_pem,
        ),
        RuntimeAuthorizationKeySet(1, (verification,)),
        PyJwtEd25519SignatureProvider(),
        issuer="verifiable-ai-governance:production",
    )


def _scope(**updates: object) -> GovernedRoutingScope:
    model = GovernedRoutingModel(
        id="44444444-4444-4444-8444-444444444444",
        version=3,
        status=EntityStatus.APPROVED,
        routing_group="reasoning-strong",
        allowed_data_classes=(DataClassification.RESTRICTED.value,),
        approved_scope_digest="a" * 64,
        next_review_at=NOW + timedelta(days=30),
        scope_digest_matches=True,
        model_version="2026.08.0",
    )
    values: dict[str, object] = {
        "ai_system_id": "22222222-2222-4222-8222-222222222222",
        "ai_system_version": 4,
        "ai_system_owner_id": "owner",
        "ai_system_status": EntityStatus.ACTIVE,
        "risk_tier": RiskTier.HIGH,
        "data_classification": DataClassification.RESTRICTED,
        "initiative_id": "11111111-1111-4111-8111-111111111111",
        "agent_id": "33333333-3333-4333-8333-333333333333",
        "agent_version": 7,
        "agent_name": "Agente de Parecer de Crédito PJ",
        "agent_owner_id": "agent-owner",
        "agent_status": EntityStatus.APPROVED,
        "agent_approved_scope_digest": "b" * 64,
        "agent_next_review_at": NOW + timedelta(days=30),
        "agent_allowed_model_ids": (model.id,),
        "agent_max_cost": Decimal("1.00"),
        "models": (model,),
        "agent_scope_digest_matches": True,
        "agent_autonomy_level": AutonomyLevel.A2_PREPARE_FOR_APPROVAL,
        "agent_tools": ("policy-mcp:read",),
        "agent_permissions": ("credit:analysis:read",),
        "agent_max_runtime_seconds": 30,
        "agent_human_approval_points": ("final-credit-approval",),
        "agent_kill_switch_enabled": True,
    }
    values.update(updates)
    return GovernedRoutingScope(**values)


def _command() -> ModelRoutingCommand:
    return ModelRoutingCommand(
        workflow_id="credit-analysis-2026-001",
        task_id="draft-opinion",
        workload=RoutingWorkload.OPINION_DRAFTING,
        context_tokens_estimated=3000,
        max_output_tokens_estimated=900,
        structured_output_required=False,
        max_latency_ms=30_000,
        max_cost_usd=Decimal("0.30"),
    )


def _issuer() -> GovernanceRuntimeAuthorizationIssuer:
    return GovernanceRuntimeAuthorizationIssuer(
        _signer(),
        RuntimeAuthorizationIssuancePolicy(
            issuer="verifiable-ai-governance:production",
            audience=("policy-model-router",),
            lifetime_seconds=300,
            policy_id="baseline-governance-policy",
            policy_version="1.0.0",
            policy_digest="d" * 64,
            control_catalog_id="verifiable-ai-governance-baseline",
            control_catalog_version="1.0.0",
            control_catalog_digest="e" * 64,
        ),
    )


def test_issuance_binds_request_scope_and_real_router_group() -> None:
    scope = _scope()
    envelope = _issuer().issue(
        scope,
        _command(),
        authorization_id="55555555-5555-4555-8555-555555555555",
        issued_at=NOW,
    )

    assert envelope.claims.scope_digest == scope.digest
    assert envelope.claims.request.workload == "opinion_drafting"
    assert envelope.claims.request.max_cost_usd_micros == 300_000
    assert envelope.claims.scope.models[0].routing_group == "reasoning-strong"
    assert envelope.claims.subject.agent_review_digest == "b" * 64
    assert envelope.claims.expires_at == NOW + timedelta(minutes=5)


def test_issuance_rejects_agent_without_runtime_limit() -> None:
    with pytest.raises(RuntimeAuthorizationIssuanceError):
        _issuer().issue(
            _scope(agent_max_runtime_seconds=None),
            _command(),
            authorization_id="55555555-5555-4555-8555-555555555555",
            issued_at=NOW,
        )


def test_issuance_rejects_kill_switch_disabled() -> None:
    with pytest.raises(RuntimeAuthorizationIssuanceError):
        _issuer().issue(
            _scope(agent_kill_switch_enabled=False),
            _command(),
            authorization_id="55555555-5555-4555-8555-555555555555",
            issued_at=NOW,
        )

from datetime import UTC, datetime

import pytest
from ai_governance_api.application.runtime_assurance_responses import (
    RuntimeAssuranceResponseService,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance import RuntimeAssuranceBreachReason
from ai_governance_api.domain.runtime_assurance_responses import (
    RuntimeAssuranceResponseAction,
    RuntimeAssuranceResponseContext,
    RuntimeAssuranceResponseRecommendation,
)
from ai_governance_api.errors import ApplicationError
from governance_schemas import RiskTier

NOW = datetime(2026, 8, 9, 19, 30, tzinfo=UTC)


def source_context(
    *,
    status: IncidentStatus = IncidentStatus.OPEN,
    severity: RiskTier = RiskTier.CRITICAL,
) -> RuntimeAssuranceResponseContext:
    return RuntimeAssuranceResponseContext(
        promotion_id="promotion-1",
        evaluation_id="evaluation-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        incident_id="incident-1",
        breach_fingerprint="b" * 64,
        source_evidence_digest="e" * 64,
        breach_reasons=(RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED,),
        incident_status=status,
        incident_severity=severity,
        incident_version=3,
        ai_system_owner_id="system-owner",
        kill_switch_enabled=True,
        kill_switch_engaged=False,
    )


class Repository:
    def __init__(self) -> None:
        self.context = source_context()
        self.existing: RuntimeAssuranceResponseRecommendation | None = None
        self.saved: RuntimeAssuranceResponseRecommendation | None = None

    async def get_context(self, promotion_id: str, *, for_update: bool = False):
        assert promotion_id == "promotion-1"
        return self.context

    async def get_recommendation_by_promotion(self, promotion_id: str):
        assert promotion_id == "promotion-1"
        return self.existing

    async def save_recommendation(self, recommendation):
        self.saved = recommendation
        return recommendation


class Audit:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def append(self, **kwargs) -> None:
        self.events.append(kwargs)


class Transaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def service(repository: Repository, audit: Audit, transaction: Transaction):
    return RuntimeAssuranceResponseService(
        repository,
        audit,
        transaction,
        clock=lambda: NOW,
        id_factory=lambda: "recommendation-1",
    )


async def test_generate_persists_advisory_evidence_and_audit() -> None:
    repository = Repository()
    audit = Audit()
    transaction = Transaction()

    result = await service(repository, audit, transaction).generate(
        promotion_id="promotion-1",
        principal=Principal(user_id="system-owner"),
    )

    assert result.id == "recommendation-1"
    assert result.advisory_only is True
    assert RuntimeAssuranceResponseAction.CONSIDER_KILL_SWITCH in result.actions
    assert repository.saved == result
    assert transaction.commits == 1
    assert audit.events[0]["action"] == "runtime_assurance.response_recommended"
    assert "rationale_codes" not in audit.events[0]["payload"]


async def test_generate_is_idempotent_per_promotion() -> None:
    repository = Repository()
    audit = Audit()
    transaction = Transaction()
    first = await service(repository, audit, transaction).generate(
        promotion_id="promotion-1",
        principal=Principal(user_id="system-owner"),
    )
    repository.existing = first
    repository.saved = None
    audit.events.clear()

    replay = await service(repository, audit, transaction).generate(
        promotion_id="promotion-1",
        principal=Principal(user_id="system-owner"),
    )

    assert replay == first
    assert repository.saved is None
    assert audit.events == []
    assert transaction.commits == 1


async def test_agent_owner_alone_cannot_generate_incident_response_advice() -> None:
    repository = Repository()
    audit = Audit()
    transaction = Transaction()

    with pytest.raises(ApplicationError, match="AI system owner"):
        await service(repository, audit, transaction).generate(
            promotion_id="promotion-1",
            principal=Principal(user_id="agent-owner"),
        )


async def test_closed_incident_cannot_generate_new_runtime_response_advice() -> None:
    repository = Repository()
    repository.context = source_context(status=IncidentStatus.CLOSED)
    audit = Audit()
    transaction = Transaction()

    with pytest.raises(ApplicationError, match="closed incident"):
        await service(repository, audit, transaction).generate(
            promotion_id="promotion-1",
            principal=Principal(user_id="system-owner"),
        )


async def test_existing_recommendation_replays_after_incident_is_closed() -> None:
    repository = Repository()
    audit = Audit()
    transaction = Transaction()
    first = await service(repository, audit, transaction).generate(
        promotion_id="promotion-1",
        principal=Principal(user_id="system-owner"),
    )
    repository.existing = first
    repository.context = source_context(status=IncidentStatus.CLOSED)
    audit.events.clear()

    replay = await service(repository, audit, transaction).generate(
        promotion_id="promotion-1",
        principal=Principal(user_id="system-owner"),
    )

    assert replay == first
    assert audit.events == []

from datetime import UTC, datetime, timedelta

import pytest
from ai_governance_api.application.runtime_assurance import RuntimeAssuranceScope
from ai_governance_api.application.runtime_assurance_incidents import (
    RuntimeAssuranceIncidentPromotionService,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import IncidentRecord, IncidentStatus
from ai_governance_api.domain.runtime_assurance import (
    RuntimeAssuranceBreachReason,
    RuntimeAssuranceEvaluation,
    RuntimeAssuranceOutcome,
)
from ai_governance_api.domain.runtime_assurance_incidents import (
    RuntimeAssuranceIncidentDisposition,
    RuntimeAssuranceIncidentPromotion,
    runtime_assurance_breach_fingerprint,
)
from ai_governance_api.errors import ApplicationError
from governance_schemas import RiskTier

NOW = datetime(2026, 8, 9, 18, 30, tzinfo=UTC)


def evaluation(
    *,
    evaluation_id: str = "eval-1",
    outcome: RuntimeAssuranceOutcome = RuntimeAssuranceOutcome.BREACHED,
    severity: RiskTier | None = RiskTier.HIGH,
    reasons: tuple[RuntimeAssuranceBreachReason, ...] = (
        RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED,
    ),
) -> RuntimeAssuranceEvaluation:
    return RuntimeAssuranceEvaluation(
        id=evaluation_id,
        agent_id="agent-1",
        ai_system_id="system-1",
        initiative_id="initiative-1",
        policy_version=2,
        evaluated_at=NOW - timedelta(seconds=5),
        window_started_at=NOW - timedelta(minutes=5),
        window_ended_at=NOW - timedelta(seconds=5),
        sample_count=10,
        duration_sample_count=10,
        failure_count=5,
        failure_rate=0.5,
        p95_duration_ms=200.0,
        max_consecutive_failures=2,
        outcome=outcome,
        breach_reasons=reasons,
        severity=severity,
        source_event_ids=("event-1", "event-2"),
        evidence_digest="a" * 64,
        version=1,
    )


def incident(
    *,
    incident_id: str = "incident-1",
    severity: RiskTier = RiskTier.HIGH,
    status: IncidentStatus = IncidentStatus.OPEN,
    version: int = 1,
) -> IncidentRecord:
    return IncidentRecord(
        id=incident_id,
        ai_system_id="system-1",
        title="Runtime assurance breach",
        severity=severity,
        status=status,
        description="structural evidence only",
        detected_at=NOW - timedelta(minutes=1),
        owner_id="system-owner",
        containment=None,
        remediation_owner_id=None,
        remediation_description=None,
        remediation_due_at=None,
        resolved_at=None,
        version=version,
        created_at=NOW - timedelta(minutes=1),
        updated_at=NOW - timedelta(minutes=1),
    )


class PromotionRepository:
    def __init__(self) -> None:
        self.evaluations: dict[str, RuntimeAssuranceEvaluation] = {}
        self.promotions: dict[str, RuntimeAssuranceIncidentPromotion] = {}
        self.active_incident_ids: list[str] = []
        self.saved_promotions: list[RuntimeAssuranceIncidentPromotion] = []
        self.scope = RuntimeAssuranceScope(
            agent_id="agent-1",
            ai_system_id="system-1",
            initiative_id="initiative-1",
            agent_owner_id="agent-owner",
            ai_system_owner_id="system-owner",
        )

    async def get_evaluation(self, evaluation_id: str):
        return self.evaluations.get(evaluation_id)

    async def get_scope(self, agent_id: str, *, for_update: bool = False):
        del for_update
        return self.scope if agent_id == self.scope.agent_id else None

    async def get_promotion_by_evaluation(self, evaluation_id: str):
        return self.promotions.get(evaluation_id)

    async def list_active_incident_ids_for_fingerprint(
        self,
        *,
        agent_id: str,
        breach_fingerprint: str,
        limit: int,
    ):
        del agent_id, breach_fingerprint
        return self.active_incident_ids[:limit]

    async def save_promotion(self, promotion: RuntimeAssuranceIncidentPromotion):
        self.promotions[promotion.evaluation_id] = promotion
        self.saved_promotions.append(promotion)
        return promotion


class IncidentRepository:
    def __init__(self) -> None:
        self.incidents: dict[str, IncidentRecord] = {}
        self.saved: list[IncidentRecord] = []

    async def get_incident(self, incident_id: str):
        return self.incidents.get(incident_id)

    async def save_incident(self, record: IncidentRecord):
        self.incidents[record.id] = record
        self.saved.append(record)
        return record


class Audit:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def append(self, **kwargs):
        self.events.append(kwargs)


class Transaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def make_service():
    promotions = PromotionRepository()
    incidents = IncidentRepository()
    audit = Audit()
    transaction = Transaction()
    ids = iter(("incident-new", "promotion-new", "promotion-next"))
    service = RuntimeAssuranceIncidentPromotionService(
        promotions,
        incidents,  # type: ignore[arg-type]
        audit,  # type: ignore[arg-type]
        transaction,  # type: ignore[arg-type]
        clock=lambda: NOW,
        id_factory=lambda: next(ids),
    )
    return service, promotions, incidents, audit, transaction


async def test_only_breached_evaluation_can_be_promoted() -> None:
    service, promotions, _, _, _ = make_service()
    promotions.evaluations["eval-1"] = evaluation(
        outcome=RuntimeAssuranceOutcome.HEALTHY,
        severity=None,
        reasons=(),
    )
    with pytest.raises(ApplicationError, match="Only a breached"):
        await service.promote(
            evaluation_id="eval-1",
            principal=Principal(user_id="system-owner"),
        )


async def test_agent_owner_does_not_gain_incident_authority() -> None:
    service, promotions, _, _, _ = make_service()
    promotions.evaluations["eval-1"] = evaluation()
    with pytest.raises(ApplicationError, match="AI system owner"):
        await service.promote(
            evaluation_id="eval-1",
            principal=Principal(user_id="agent-owner"),
        )


async def test_first_breach_creates_governed_incident_and_linkage() -> None:
    service, promotions, incidents, audit, transaction = make_service()
    promotions.evaluations["eval-1"] = evaluation()

    result = await service.promote(
        evaluation_id="eval-1",
        principal=Principal(user_id="system-owner"),
    )

    assert result.promotion.disposition is RuntimeAssuranceIncidentDisposition.CREATED
    assert result.incident.id == "incident-new"
    assert result.incident.status is IncidentStatus.OPEN
    assert result.incident.owner_id == "system-owner"
    assert len(incidents.saved) == 1
    assert len(promotions.saved_promotions) == 1
    assert [event["action"] for event in audit.events] == [
        "incident.reported",
        "runtime_assurance.incident_promoted",
    ]
    assert transaction.commits == 1


async def test_same_breach_family_deduplicates_to_active_incident() -> None:
    service, promotions, incidents, audit, transaction = make_service()
    current = incident()
    incidents.incidents[current.id] = current
    promotions.active_incident_ids = [current.id]
    promotions.evaluations["eval-1"] = evaluation()

    result = await service.promote(
        evaluation_id="eval-1",
        principal=Principal(user_id="system-owner"),
    )

    assert result.promotion.disposition is (RuntimeAssuranceIncidentDisposition.DEDUPLICATED)
    assert result.incident.id == current.id
    assert incidents.saved == []
    assert [event["action"] for event in audit.events] == ["runtime_assurance.incident_promoted"]
    assert transaction.commits == 1


async def test_higher_breach_severity_escalates_same_incident() -> None:
    service, promotions, incidents, audit, _ = make_service()
    current = incident(severity=RiskTier.MEDIUM, version=3)
    incidents.incidents[current.id] = current
    promotions.active_incident_ids = [current.id]
    promotions.evaluations["eval-1"] = evaluation(severity=RiskTier.CRITICAL)

    result = await service.promote(
        evaluation_id="eval-1",
        principal=Principal(user_id="system-owner"),
    )

    assert result.promotion.disposition is (RuntimeAssuranceIncidentDisposition.SEVERITY_ESCALATED)
    assert result.incident.severity is RiskTier.CRITICAL
    assert result.incident.version == 4
    assert [event["action"] for event in audit.events] == [
        "incident.severity_escalated",
        "runtime_assurance.incident_promoted",
    ]


async def test_same_evaluation_is_idempotent() -> None:
    service, promotions, incidents, audit, transaction = make_service()
    current = incident()
    incidents.incidents[current.id] = current
    existing = RuntimeAssuranceIncidentPromotion(
        id="promotion-existing",
        evaluation_id="eval-1",
        agent_id="agent-1",
        ai_system_id="system-1",
        incident_id=current.id,
        breach_fingerprint=runtime_assurance_breach_fingerprint(
            agent_id="agent-1",
            breach_reasons=(RuntimeAssuranceBreachReason.FAILURE_RATE_EXCEEDED,),
        ),
        disposition=RuntimeAssuranceIncidentDisposition.CREATED,
        promoted_by="system-owner",
        promoted_at=NOW,
        evidence_digest="a" * 64,
    )
    promotions.promotions["eval-1"] = existing
    promotions.evaluations["eval-1"] = evaluation()

    result = await service.promote(
        evaluation_id="eval-1",
        principal=Principal(user_id="system-owner"),
    )

    assert result.promotion == existing
    assert promotions.saved_promotions == []
    assert incidents.saved == []
    assert audit.events == []
    assert transaction.commits == 0


async def test_multiple_active_matches_fail_closed() -> None:
    service, promotions, _, _, transaction = make_service()
    promotions.evaluations["eval-1"] = evaluation()
    promotions.active_incident_ids = ["incident-1", "incident-2"]

    with pytest.raises(ApplicationError, match="Multiple active incidents"):
        await service.promote(
            evaluation_id="eval-1",
            principal=Principal(user_id="system-owner"),
        )
    assert transaction.commits == 0

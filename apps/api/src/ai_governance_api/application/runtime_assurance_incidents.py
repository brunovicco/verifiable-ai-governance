"""Explicit Runtime Assurance breach-to-incident promotion and deduplication."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from ai_governance_api.application.incidents import (
    IncidentAuditPort,
    IncidentRepositoryPort,
    IncidentTransactionPort,
)
from ai_governance_api.application.runtime_assurance import RuntimeAssuranceScope
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.incidents import IncidentRecord, IncidentStatus
from ai_governance_api.domain.runtime_assurance import (
    RuntimeAssuranceEvaluation,
    RuntimeAssuranceOutcome,
)
from ai_governance_api.domain.runtime_assurance_incidents import (
    RuntimeAssuranceIncidentDisposition,
    RuntimeAssuranceIncidentPromotion,
    RuntimeAssuranceIncidentPromotionResult,
    runtime_assurance_breach_fingerprint,
    should_escalate_incident_severity,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]


class RuntimeAssuranceIncidentPromotionRepositoryPort(Protocol):
    """Persistence boundary for assurance evaluations and promotion link evidence."""

    async def get_evaluation(
        self,
        evaluation_id: str,
    ) -> RuntimeAssuranceEvaluation | None:
        """Return one immutable assurance evaluation."""
        ...

    async def get_scope(
        self,
        agent_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeAssuranceScope | None:
        """Return trusted Agent ownership facts, optionally locking the AI System."""
        ...

    async def get_promotion_by_evaluation(
        self,
        evaluation_id: str,
    ) -> RuntimeAssuranceIncidentPromotion | None:
        """Return an existing idempotency binding for one evaluation."""
        ...

    async def list_active_incident_ids_for_fingerprint(
        self,
        *,
        agent_id: str,
        breach_fingerprint: str,
        limit: int,
    ) -> list[str]:
        """Return active incidents already linked to the same breach family."""
        ...

    async def save_promotion(
        self,
        promotion: RuntimeAssuranceIncidentPromotion,
    ) -> RuntimeAssuranceIncidentPromotion:
        """Persist one append-only evaluation-to-incident binding."""
        ...


class RuntimeAssuranceIncidentPromotionService:
    """Promote breached evaluations into existing governed incident lifecycle."""

    def __init__(
        self,
        promotion_repository: RuntimeAssuranceIncidentPromotionRepositoryPort,
        incident_repository: IncidentRepositoryPort,
        audit: IncidentAuditPort,
        transaction: IncidentTransactionPort,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialize explicit I/O boundaries and deterministic test seams."""
        self._promotion_repository = promotion_repository
        self._incident_repository = incident_repository
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def promote(
        self,
        *,
        evaluation_id: str,
        principal: Principal,
    ) -> RuntimeAssuranceIncidentPromotionResult:
        """Create, deduplicate, or severity-escalate a governed incident."""
        evaluation = await self._require_evaluation(evaluation_id)
        self._require_breached(evaluation)

        scope = await self._promotion_repository.get_scope(
            evaluation.agent_id,
            for_update=True,
        )
        if (
            scope is None
            or scope.ai_system_id != evaluation.ai_system_id
            or scope.initiative_id != evaluation.initiative_id
        ):
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Runtime assurance evaluation no longer matches its governed Agent",
            )
        self._require_system_owner_or_admin(scope, principal)

        existing = await self._promotion_repository.get_promotion_by_evaluation(evaluation.id)
        if existing is not None:
            incident = await self._require_linked_incident(existing.incident_id)
            return RuntimeAssuranceIncidentPromotionResult(
                promotion=existing,
                incident=incident,
            )

        breach_fingerprint = runtime_assurance_breach_fingerprint(
            agent_id=evaluation.agent_id,
            breach_reasons=evaluation.breach_reasons,
        )
        active_incident_ids = (
            await self._promotion_repository.list_active_incident_ids_for_fingerprint(
                agent_id=evaluation.agent_id,
                breach_fingerprint=breach_fingerprint,
                limit=2,
            )
        )
        if len(active_incident_ids) > 1:
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Multiple active incidents match the Runtime Assurance breach",
            )

        now = self._clock()
        try:
            incident, disposition, incident_audit = await self._resolve_incident_for_promotion(
                evaluation=evaluation,
                scope=scope,
                active_incident_ids=active_incident_ids,
                breach_fingerprint=breach_fingerprint,
                now=now,
            )
            promotion = RuntimeAssuranceIncidentPromotion(
                id=self._id_factory(),
                evaluation_id=evaluation.id,
                agent_id=evaluation.agent_id,
                ai_system_id=evaluation.ai_system_id,
                incident_id=incident.id,
                breach_fingerprint=breach_fingerprint,
                disposition=disposition,
                promoted_by=principal.user_id,
                promoted_at=now,
                evidence_digest=evaluation.evidence_digest,
            )

            if incident_audit is not None:
                action, payload = incident_audit
                await self._audit.append(
                    actor_id=principal.user_id,
                    action=action,
                    entity_type="incident",
                    entity_id=incident.id,
                    entity_version=incident.version,
                    payload=payload,
                )

            promotion = await self._promotion_repository.save_promotion(promotion)
            await self._audit.append(
                actor_id=principal.user_id,
                action="runtime_assurance.incident_promoted",
                entity_type="runtime_assurance_incident_promotion",
                entity_id=promotion.id,
                entity_version=promotion.version,
                payload={
                    "evaluation_id": promotion.evaluation_id,
                    "incident_id": promotion.incident_id,
                    "agent_id": promotion.agent_id,
                    "ai_system_id": promotion.ai_system_id,
                    "disposition": promotion.disposition.value,
                    "breach_fingerprint": promotion.breach_fingerprint,
                    "evidence_digest": promotion.evidence_digest,
                },
            )
            await self._transaction.commit()
            return RuntimeAssuranceIncidentPromotionResult(
                promotion=promotion,
                incident=incident,
            )
        except Exception:
            await self._transaction.rollback()
            raise

    async def _resolve_incident_for_promotion(
        self,
        *,
        evaluation: RuntimeAssuranceEvaluation,
        scope: RuntimeAssuranceScope,
        active_incident_ids: list[str],
        breach_fingerprint: str,
        now: datetime,
    ) -> tuple[
        IncidentRecord,
        RuntimeAssuranceIncidentDisposition,
        tuple[str, dict[str, object]] | None,
    ]:
        """Create/deduplicate an incident and describe any required incident audit."""
        severity = evaluation.severity
        if severity is None:
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Breached Runtime Assurance evaluation has no severity",
            )

        if active_incident_ids:
            incident = await self._require_linked_incident(active_incident_ids[0])
            if should_escalate_incident_severity(
                current=incident.severity,
                observed=severity,
            ):
                previous_severity = incident.severity
                updated = replace(
                    incident,
                    severity=severity,
                    version=incident.version + 1,
                    updated_at=now,
                )
                updated = await self._incident_repository.save_incident(updated)
                return (
                    updated,
                    RuntimeAssuranceIncidentDisposition.SEVERITY_ESCALATED,
                    (
                        "incident.severity_escalated",
                        {
                            "ai_system_id": updated.ai_system_id,
                            "status": updated.status.value,
                            "previous_severity": previous_severity.value,
                            "severity": updated.severity.value,
                            "source": "runtime_assurance",
                            "source_evaluation_id": evaluation.id,
                            "source_agent_id": evaluation.agent_id,
                            "breach_fingerprint": breach_fingerprint,
                        },
                    ),
                )
            return (
                incident,
                RuntimeAssuranceIncidentDisposition.DEDUPLICATED,
                None,
            )

        incident = IncidentRecord(
            id=self._id_factory(),
            ai_system_id=evaluation.ai_system_id,
            title="Runtime assurance breach",
            severity=severity,
            status=IncidentStatus.OPEN,
            description=self._incident_description(evaluation),
            detected_at=evaluation.evaluated_at,
            owner_id=scope.ai_system_owner_id,
            containment=None,
            remediation_owner_id=None,
            remediation_description=None,
            remediation_due_at=None,
            resolved_at=None,
            version=1,
            created_at=now,
            updated_at=now,
        )
        incident = await self._incident_repository.save_incident(incident)
        return (
            incident,
            RuntimeAssuranceIncidentDisposition.CREATED,
            (
                "incident.reported",
                {
                    "ai_system_id": incident.ai_system_id,
                    "status": incident.status.value,
                    "severity": incident.severity.value,
                    "source": "runtime_assurance",
                    "source_evaluation_id": evaluation.id,
                    "source_agent_id": evaluation.agent_id,
                    "breach_fingerprint": breach_fingerprint,
                },
            ),
        )

    async def get_promotion(
        self,
        *,
        evaluation_id: str,
        principal: Principal,
    ) -> RuntimeAssuranceIncidentPromotionResult:
        """Return the persisted promotion visible to the system owner or admin."""
        evaluation = await self._require_evaluation(evaluation_id)
        scope = await self._promotion_repository.get_scope(
            evaluation.agent_id,
        )
        if scope is None or scope.ai_system_id != evaluation.ai_system_id:
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Runtime assurance evaluation no longer matches its governed Agent",
            )
        self._require_system_owner_or_admin(scope, principal)
        promotion = await self._promotion_repository.get_promotion_by_evaluation(evaluation_id)
        if promotion is None:
            raise ApplicationError(
                ErrorKind.NOT_FOUND,
                "Runtime Assurance incident promotion not found",
            )
        incident = await self._require_linked_incident(promotion.incident_id)
        return RuntimeAssuranceIncidentPromotionResult(
            promotion=promotion,
            incident=incident,
        )

    async def _require_evaluation(
        self,
        evaluation_id: str,
    ) -> RuntimeAssuranceEvaluation:
        evaluation = await self._promotion_repository.get_evaluation(evaluation_id)
        if evaluation is None:
            raise ApplicationError(
                ErrorKind.NOT_FOUND,
                "Runtime assurance evaluation not found",
            )
        return evaluation

    def _require_breached(
        self,
        evaluation: RuntimeAssuranceEvaluation,
    ) -> None:
        if (
            evaluation.outcome is not RuntimeAssuranceOutcome.BREACHED
            or not evaluation.breach_reasons
            or evaluation.severity is None
        ):
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Only a breached Runtime Assurance evaluation can be promoted",
            )

    def _require_system_owner_or_admin(
        self,
        scope: RuntimeAssuranceScope,
        principal: Principal,
    ) -> None:
        if principal.user_id != scope.ai_system_owner_id and not principal.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only the AI system owner or an administrator "
                "can promote a Runtime Assurance breach",
            )

    async def _require_linked_incident(
        self,
        incident_id: str,
    ) -> IncidentRecord:
        incident = await self._incident_repository.get_incident(incident_id)
        if incident is None:
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Runtime Assurance promotion references an unavailable incident",
            )
        return incident

    def _incident_description(
        self,
        evaluation: RuntimeAssuranceEvaluation,
    ) -> str:
        reasons = ",".join(sorted(reason.value for reason in evaluation.breach_reasons))
        return (
            "Promoted from deterministic Runtime Assurance breach evidence. "
            f"Agent={evaluation.agent_id}; reasons={reasons}; "
            f"evidence_digest={evaluation.evidence_digest}."
        )

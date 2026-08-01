"""Application service for initiative lifecycle use cases."""

import hashlib
from datetime import UTC, datetime
from typing import Protocol

from governance_schemas import (
    ApprovalStatus,
    EntityStatus,
    PolicyContext,
    PolicyDecision,
    RiskTier,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_governance_api.audit import append_audit_event
from ai_governance_api.auth import Principal
from ai_governance_api.errors import ApplicationError, ErrorKind
from ai_governance_api.models import Approval, AuditEvent, Evidence, Initiative
from ai_governance_api.schemas import (
    ApprovalDecisionRequest,
    InitiativeCreate,
    SubmissionRequest,
)


class PolicyEvaluator(Protocol):
    """Port implemented by deterministic or external policy evaluators."""

    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        """Evaluate a complete policy context without mutating it."""
        ...


class InitiativeService:
    """Coordinate initiative use cases and their transactional audit trail."""

    def __init__(self, session: AsyncSession, policy_evaluator: PolicyEvaluator) -> None:
        """Create a service with explicit persistence and policy dependencies."""
        self._session = session
        self._policy_evaluator = policy_evaluator

    async def create(self, request: InitiativeCreate, principal: Principal) -> Initiative:
        """Create an initiative and record its initial policy decision."""
        decision = self._policy_evaluator.evaluate(self._policy_context(request))
        initiative = Initiative(
            **request.model_dump(),
            business_owner_id=principal.user_id,
            risk_score=decision.score,
            risk_tier=decision.tier,
            policy_id=decision.policy_id,
            policy_version=decision.policy_version,
            required_documents=decision.required_documents,
        )
        self._session.add(initiative)
        await self._session.flush()
        await append_audit_event(
            self._session,
            actor_id=principal.user_id,
            action="initiative.created",
            entity_type="initiative",
            entity_id=initiative.id,
            entity_version=initiative.version,
            payload={"risk_score": decision.score, "risk_tier": decision.tier.value},
        )
        await self._session.commit()
        return await self.get(initiative.id)

    async def list_initiatives(self) -> list[Initiative]:
        """Return initiatives ordered from newest to oldest."""
        result = await self._session.scalars(
            select(Initiative).order_by(Initiative.created_at.desc())
        )
        return list(result)

    async def get(self, initiative_id: str) -> Initiative:
        """Load an initiative aggregate or raise a stable not-found error."""
        initiative = await self._session.scalar(
            select(Initiative)
            .where(Initiative.id == initiative_id)
            .options(selectinload(Initiative.approvals), selectinload(Initiative.systems))
        )
        if initiative is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Initiative not found")
        return initiative

    async def submit(
        self,
        initiative_id: str,
        request: SubmissionRequest,
        principal: Principal,
    ) -> Initiative:
        """Submit a draft initiative and create its approval gates."""
        initiative = await self.get(initiative_id)
        self._validate_submission(initiative, request, principal)

        decision = self._policy_evaluator.evaluate(self._policy_context(initiative))
        if not decision.can_submit:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                {
                    "message": "Policy blocked submission",
                    "reasons": decision.blocked_reasons,
                },
            )

        now = datetime.now(UTC)
        initiative.approvals.extend(self._approval_gates(decision, now))
        self._apply_submission_decision(initiative, decision, now)
        await self._session.flush()
        await append_audit_event(
            self._session,
            actor_id=principal.user_id,
            action="initiative.submitted",
            entity_type="initiative",
            entity_id=initiative.id,
            entity_version=initiative.version,
            payload={
                "policy_id": decision.policy_id,
                "policy_version": decision.policy_version,
                "required_approvals": [
                    item.area.value for item in decision.approvals if item.required
                ],
                "required_documents": decision.required_documents,
            },
        )
        await self._session.commit()
        return await self.get(initiative.id)

    async def decide_approval(
        self,
        initiative_id: str,
        approval_id: str,
        request: ApprovalDecisionRequest,
        principal: Principal,
    ) -> Initiative:
        """Record an independent approval decision and its evidence digest."""
        initiative = await self.get(initiative_id)
        approval = self._find_approval(initiative, approval_id)
        self._validate_approval(initiative, approval, request, principal)

        approval.status = request.decision
        approval.comments = request.comments
        approval.decided_by = principal.user_id
        approval.decided_at = datetime.now(UTC)
        approval.version += 1
        evidence_digest = self._evidence_digest(approval.id, principal.user_id, request)
        self._session.add(
            Evidence(
                initiative_id=initiative.id,
                approval_id=approval.id,
                kind="approval-attestation",
                uri=request.evidence_uri,
                sha256=evidence_digest,
                supplied_by=principal.user_id,
                trusted_source=False,
                metadata_json={"area": approval.area.value, "decision": request.decision.value},
            )
        )

        initiative.status = self._resulting_status(initiative.approvals)
        initiative.version += 1
        await self._session.flush()
        await append_audit_event(
            self._session,
            actor_id=principal.user_id,
            action="approval.decided",
            entity_type="initiative",
            entity_id=initiative.id,
            entity_version=initiative.version,
            payload={
                "approval_id": approval.id,
                "area": approval.area.value,
                "decision": approval.status.value,
                "evidence_sha256": evidence_digest,
                "resulting_status": initiative.status.value,
            },
        )
        await self._session.commit()
        return await self.get(initiative.id)

    async def list_audit_events(self, initiative_id: str) -> list[AuditEvent]:
        """Return the ordered audit trail for an existing initiative."""
        await self.get(initiative_id)
        events = await self._session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == "initiative",
                AuditEvent.entity_id == initiative_id,
            )
            .order_by(AuditEvent.occurred_at)
        )
        return list(events)

    @staticmethod
    def _policy_context(source: Initiative | InitiativeCreate) -> PolicyContext:
        return PolicyContext(
            decision_impact=source.decision_impact,
            data_classification=source.data_classification,
            autonomy_level=source.autonomy_level,
            hosting_model=source.hosting_model,
            affects_rights=source.affects_rights,
            executes_actions=source.executes_actions,
            personal_data=source.personal_data,
            sensitive_data=source.sensitive_data,
            children_data=source.children_data,
            external_facing=source.external_facing,
            regulated_context=source.regulated_context,
            international_processing=source.international_processing,
            uses_rag=source.uses_rag,
            uses_agents=source.uses_agents,
            uses_mcp=source.uses_mcp,
            uses_custom_model=source.uses_custom_model,
        )

    @staticmethod
    def _validate_submission(
        initiative: Initiative,
        request: SubmissionRequest,
        principal: Principal,
    ) -> None:
        if initiative.business_owner_id != principal.user_id:
            raise ApplicationError(ErrorKind.FORBIDDEN, "Only the owner can submit")
        if initiative.status is not EntityStatus.DRAFT:
            raise ApplicationError(ErrorKind.CONFLICT, "Initiative is not a draft")
        if initiative.version != request.expected_version:
            raise ApplicationError(ErrorKind.CONFLICT, "Version conflict")
        if initiative.approvals:
            raise ApplicationError(ErrorKind.CONFLICT, "Approval gates already exist")

    @staticmethod
    def _approval_gates(decision: PolicyDecision, requested_at: datetime) -> list[Approval]:
        return [
            Approval(
                area=requirement.area,
                required=requirement.required,
                reason=requirement.reason,
                status=(
                    ApprovalStatus.PENDING if requirement.required else ApprovalStatus.NOT_REQUIRED
                ),
                requested_at=requested_at if requirement.required else None,
            )
            for requirement in decision.approvals
        ]

    @staticmethod
    def _apply_submission_decision(
        initiative: Initiative,
        decision: PolicyDecision,
        submitted_at: datetime,
    ) -> None:
        initiative.status = EntityStatus.UNDER_REVIEW
        initiative.submitted_at = submitted_at
        initiative.version += 1
        initiative.risk_score = decision.score
        initiative.risk_tier = decision.tier
        initiative.policy_id = decision.policy_id
        initiative.policy_version = decision.policy_version
        initiative.required_documents = decision.required_documents

    @staticmethod
    def _find_approval(initiative: Initiative, approval_id: str) -> Approval:
        approval = next((item for item in initiative.approvals if item.id == approval_id), None)
        if approval is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Approval not found")
        return approval

    @staticmethod
    def _validate_approval(
        initiative: Initiative,
        approval: Approval,
        request: ApprovalDecisionRequest,
        principal: Principal,
    ) -> None:
        if not approval.required or approval.status is not ApprovalStatus.PENDING:
            raise ApplicationError(ErrorKind.CONFLICT, "Approval is not pending")
        if approval.version != request.expected_version:
            raise ApplicationError(ErrorKind.CONFLICT, "Version conflict")
        if initiative.business_owner_id == principal.user_id:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Segregation of duties prevents owner self-approval",
            )
        if approval.area not in principal.approval_areas and not principal.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                f"Principal cannot approve for {approval.area.value}",
            )
        if initiative.risk_tier in {RiskTier.HIGH, RiskTier.CRITICAL} and any(
            item.decided_by == principal.user_id for item in initiative.approvals
        ):
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "High-risk gates require independent approvers across areas",
            )

    @staticmethod
    def _evidence_digest(
        approval_id: str,
        principal_id: str,
        request: ApprovalDecisionRequest,
    ) -> str:
        evidence = f"{approval_id}:{principal_id}:{request.evidence_uri}:{request.comments}"
        return hashlib.sha256(evidence.encode()).hexdigest()

    @staticmethod
    def _resulting_status(approvals: list[Approval]) -> EntityStatus:
        required = [item for item in approvals if item.required]
        if any(item.status is ApprovalStatus.REJECTED for item in required):
            return EntityStatus.REJECTED
        if all(item.status is ApprovalStatus.APPROVED for item in required):
            return EntityStatus.APPROVED
        return EntityStatus.UNDER_REVIEW

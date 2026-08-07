"""Application service for initiative lifecycle and immutable review rounds."""

import copy
import hashlib
from datetime import UTC, datetime
from typing import NoReturn, Protocol

from governance_schemas import ApprovalStatus, EntityStatus, PolicyContext, PolicyDecision
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_governance_api.audit import append_audit_event
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.reviews import (
    InitiativeReviewState,
    ReviewActor,
    ReviewConflict,
    ReviewForbidden,
    ReviewGateState,
    decide_gate,
    validate_resubmission,
)
from ai_governance_api.errors import ApplicationError, ErrorKind
from ai_governance_api.models import (
    Approval,
    Assessment,
    AuditEvent,
    Evidence,
    Initiative,
    ReviewSubmission,
)
from ai_governance_api.schemas import (
    ApprovalDecisionRequest,
    InitiativeCreate,
    InitiativeResubmissionRequest,
    InitiativeRevisionRequest,
    SubmissionRequest,
)


class PolicyEvaluator(Protocol):
    """Port implemented by deterministic or external policy evaluators."""

    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        """Evaluate a complete policy context without mutating it."""
        ...


class InitiativeService:
    """Coordinate initiative commands and their transactional audit trail."""

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
            .options(
                selectinload(Initiative.approvals),
                selectinload(Initiative.assessments),
                selectinload(Initiative.systems),
                selectinload(Initiative.review_submissions),
            )
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
        """Create the immutable initial review round for a draft initiative."""
        initiative = await self._get_for_update(initiative_id)
        self._validate_initial_submission(initiative, request, principal)
        decision = self._evaluate_for_submission(initiative)
        now = datetime.now(UTC)
        submission = await self._start_review_round(
            initiative,
            decision,
            principal,
            review_round=1,
            revision_summary=request.revision_summary or "Initial submission",
            submitted_at=now,
        )
        await self._append_submission_audit(
            initiative=initiative,
            submission=submission,
            decision=decision,
            actor_id=principal.user_id,
            action="initiative.submitted",
            changed_fields=(),
        )
        await self._commit_review_transition()
        return await self.get(initiative.id)

    async def resubmit(
        self,
        initiative_id: str,
        request: InitiativeResubmissionRequest,
        principal: Principal,
    ) -> Initiative:
        """Apply owner revisions and create a new immutable review round."""
        initiative = await self._get_for_update(initiative_id)
        try:
            validate_resubmission(
                self._review_state(initiative),
                expected_version=request.expected_version,
                actor=self._review_actor(principal),
            )
        except (ReviewConflict, ReviewForbidden) as exc:
            self._raise_review_error(exc)
        decision = self._evaluate_for_submission(initiative)
        self._require_assessments_ready(
            initiative.assessments,
            decision.required_documents,
        )
        now = datetime.now(UTC)
        submission = await self._start_review_round(
            initiative,
            decision,
            principal,
            review_round=initiative.current_review_round + 1,
            revision_summary=request.revision_summary,
            submitted_at=now,
        )
        await self._append_submission_audit(
            initiative=initiative,
            submission=submission,
            decision=decision,
            actor_id=principal.user_id,
            action="initiative.resubmitted",
            changed_fields=(),
        )
        await self._commit_review_transition()
        return await self.get(initiative.id)

    async def revise(
        self,
        initiative_id: str,
        request: InitiativeRevisionRequest,
        principal: Principal,
    ) -> Initiative:
        """Save corrected proposal facts without creating a review round."""
        initiative = await self._get_for_update(initiative_id)
        try:
            validate_resubmission(
                self._review_state(initiative),
                expected_version=request.expected_version,
                actor=self._review_actor(principal),
            )
        except (ReviewConflict, ReviewForbidden) as exc:
            self._raise_review_error(exc)

        requested_changes = request.changes()
        changes = {
            field: value
            for field, value in requested_changes.items()
            if getattr(initiative, field) != value
        }
        if not changes:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                "Revision does not change proposal facts",
            )
        for field, value in changes.items():
            setattr(initiative, field, value)
        if initiative.international_processing and not initiative.inference_countries:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                "Inference countries are required for international processing",
            )
        decision = self._evaluate_for_submission(initiative)
        self._apply_policy_projection(initiative, decision)
        initiative.version += 1
        await append_audit_event(
            self._session,
            actor_id=principal.user_id,
            action="initiative.revision_saved",
            entity_type="initiative",
            entity_id=initiative.id,
            entity_version=initiative.version,
            payload={
                "review_round": initiative.current_review_round,
                "changed_fields": sorted(changes),
                "change_reason_sha256": hashlib.sha256(request.change_reason.encode()).hexdigest(),
                "policy_id": decision.policy_id,
                "policy_version": decision.policy_version,
                "risk_tier": decision.tier.value,
            },
        )
        await self._commit_review_transition()
        return await self.get(initiative.id)

    async def decide_approval(
        self,
        initiative_id: str,
        approval_id: str,
        request: ApprovalDecisionRequest,
        principal: Principal,
    ) -> Initiative:
        """Record one independent gate decision within the current review round."""
        initiative = await self._get_for_update(initiative_id)
        approval = self._find_approval(initiative, approval_id)
        try:
            transition = decide_gate(
                self._review_state(initiative),
                gate_id=approval_id,
                decision=request.decision,
                expected_version=request.expected_version,
                actor=self._review_actor(principal),
            )
        except (ReviewConflict, ReviewForbidden) as exc:
            self._raise_review_error(exc)

        now = datetime.now(UTC)
        approval.status = request.decision
        approval.comments = request.comments
        approval.decided_by = principal.user_id
        approval.decided_at = now
        approval.version += 1
        for gate in initiative.approvals:
            if gate.id in transition.superseded_gate_ids:
                gate.status = ApprovalStatus.SUPERSEDED
                gate.superseded_at = now
                gate.version += 1

        reopened_assessments: list[Assessment] = []
        if transition.resulting_status is EntityStatus.CHANGES_REQUESTED:
            reopened_assessments = self._reopen_assessments(initiative.assessments, now)

        submission = self._current_submission(initiative)
        submission.status = transition.resulting_status
        submission.version += 1
        if transition.resulting_status in {
            EntityStatus.APPROVED,
            EntityStatus.REJECTED,
            EntityStatus.CHANGES_REQUESTED,
        }:
            submission.resolved_at = now
        initiative.status = transition.resulting_status
        initiative.version += 1

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
                metadata_json={
                    "area": approval.area.value,
                    "decision": request.decision.value,
                    "review_round": initiative.current_review_round,
                },
            )
        )
        await self._session.flush()
        for assessment in reopened_assessments:
            await append_audit_event(
                self._session,
                actor_id=principal.user_id,
                action="assessment.reopened",
                entity_type="assessment",
                entity_id=assessment.id,
                entity_version=assessment.version,
                payload={
                    "initiative_id": initiative.id,
                    "review_round": initiative.current_review_round,
                },
            )
        audit_payload: dict[str, object] = {
            "approval_id": approval.id,
            "area": approval.area.value,
            "decision": approval.status.value,
            "evidence_sha256": evidence_digest,
            "resulting_status": initiative.status.value,
            "review_round": initiative.current_review_round,
            "superseded_approval_ids": list(transition.superseded_gate_ids),
            "reopened_assessment_ids": [item.id for item in reopened_assessments],
        }
        if principal.authorization_provenance is not None:
            audit_payload["authorization"] = {
                "catalog_id": principal.authorization_provenance.catalog_id,
                "catalog_version": principal.authorization_provenance.catalog_version,
                "catalog_digest": principal.authorization_provenance.catalog_digest,
                "matched_mapping_ids": list(principal.authorization_provenance.matched_mapping_ids),
                "source_types": list(principal.authorization_provenance.source_types),
                "group_resolution_source": (
                    principal.authorization_provenance.group_resolution_source.value
                ),
            }
        await append_audit_event(
            self._session,
            actor_id=principal.user_id,
            action=(
                "review.changes_requested"
                if request.decision is ApprovalStatus.CHANGES_REQUESTED
                else "approval.decided"
            ),
            entity_type="initiative",
            entity_id=initiative.id,
            entity_version=initiative.version,
            payload=audit_payload,
        )
        await self._commit_review_transition()
        return await self.get(initiative.id)

    async def list_review_history(
        self,
        initiative_id: str,
        principal: Principal,
    ) -> list[ReviewSubmission]:
        """Return content-minimized review rounds to authorized participants."""
        initiative = await self.get(initiative_id)
        can_review = any(item.area in principal.approval_areas for item in initiative.approvals)
        if (
            initiative.business_owner_id != principal.user_id
            and not principal.is_admin
            and not can_review
        ):
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only the owner or a participating reviewer can view review history",
            )
        result = await self._session.scalars(
            select(ReviewSubmission)
            .where(ReviewSubmission.initiative_id == initiative_id)
            .options(selectinload(ReviewSubmission.approvals))
            .order_by(ReviewSubmission.review_round)
        )
        return list(result)

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

    async def _start_review_round(
        self,
        initiative: Initiative,
        decision: PolicyDecision,
        principal: Principal,
        *,
        review_round: int,
        revision_summary: str,
        submitted_at: datetime,
    ) -> ReviewSubmission:
        """Persist one snapshot and its fresh policy-derived approval gates."""
        submission = ReviewSubmission(
            initiative=initiative,
            review_round=review_round,
            status=EntityStatus.UNDER_REVIEW,
            submitted_by=principal.user_id,
            submitted_at=submitted_at,
            revision_summary=revision_summary,
            policy_id=decision.policy_id,
            policy_version=decision.policy_version,
            risk_score=decision.score,
            risk_tier=decision.tier,
            initiative_snapshot=self._initiative_snapshot(initiative),
            assessment_snapshots=self._assessment_snapshots(initiative.assessments),
        )
        self._session.add(submission)
        await self._session.flush()
        gates = self._approval_gates(
            initiative=initiative,
            submission=submission,
            decision=decision,
            requested_at=submitted_at,
        )
        self._session.add_all(gates)
        self._apply_submission_decision(
            initiative,
            decision,
            submitted_at,
            review_round,
        )
        await self._session.flush()
        return submission

    async def _get_for_update(self, initiative_id: str) -> Initiative:
        """Lock an initiative aggregate while a review command is evaluated."""
        initiative = await self._session.scalar(
            select(Initiative)
            .where(Initiative.id == initiative_id)
            .with_for_update()
            .options(
                selectinload(Initiative.approvals),
                selectinload(Initiative.assessments),
                selectinload(Initiative.systems),
                selectinload(Initiative.review_submissions),
            )
        )
        if initiative is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Initiative not found")
        return initiative

    async def _commit_review_transition(self) -> None:
        """Commit a review transition or expose a stable concurrency conflict."""
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Concurrent review update; reload the initiative and retry",
            ) from exc

    async def _append_submission_audit(
        self,
        *,
        initiative: Initiative,
        submission: ReviewSubmission,
        decision: PolicyDecision,
        actor_id: str,
        action: str,
        changed_fields: tuple[str, ...],
    ) -> None:
        """Append submission provenance without copying snapshot content."""
        await append_audit_event(
            self._session,
            actor_id=actor_id,
            action=action,
            entity_type="initiative",
            entity_id=initiative.id,
            entity_version=initiative.version,
            payload={
                "review_submission_id": submission.id,
                "review_round": submission.review_round,
                "policy_id": decision.policy_id,
                "policy_version": decision.policy_version,
                "required_approvals": [
                    item.area.value for item in decision.approvals if item.required
                ],
                "required_documents": decision.required_documents,
                "changed_fields": list(changed_fields),
            },
        )

    def _evaluate_for_submission(self, initiative: Initiative) -> PolicyDecision:
        """Re-evaluate the current proposal and fail closed on policy blocks."""
        decision = self._policy_evaluator.evaluate(self._policy_context(initiative))
        if not decision.can_submit:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                {
                    "message": "Policy blocked submission",
                    "reasons": decision.blocked_reasons,
                },
            )
        return decision

    @staticmethod
    def _policy_context(source: Initiative | InitiativeCreate) -> PolicyContext:
        """Map proposal facts into the provider-neutral policy contract."""
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
    def _validate_initial_submission(
        initiative: Initiative,
        request: SubmissionRequest,
        principal: Principal,
    ) -> None:
        """Require an owner-controlled, current, never-submitted draft."""
        if initiative.business_owner_id != principal.user_id:
            raise ApplicationError(ErrorKind.FORBIDDEN, "Only the owner can submit")
        if initiative.status is not EntityStatus.DRAFT:
            raise ApplicationError(ErrorKind.CONFLICT, "Initiative is not a draft")
        if initiative.version != request.expected_version:
            raise ApplicationError(ErrorKind.CONFLICT, "Version conflict")
        if initiative.current_review_round != 0 or initiative.approvals:
            raise ApplicationError(ErrorKind.CONFLICT, "Review history already exists")

    @staticmethod
    def _approval_gates(
        *,
        initiative: Initiative,
        submission: ReviewSubmission,
        decision: PolicyDecision,
        requested_at: datetime,
    ) -> list[Approval]:
        """Create fresh gates linked to one immutable submission snapshot."""
        return [
            Approval(
                initiative=initiative,
                review_submission=submission,
                review_round=submission.review_round,
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
        review_round: int,
    ) -> None:
        """Update the operational projection to the newly submitted round."""
        initiative.status = EntityStatus.UNDER_REVIEW
        initiative.submitted_at = submitted_at
        initiative.current_review_round = review_round
        initiative.version += 1
        InitiativeService._apply_policy_projection(initiative, decision)

    @staticmethod
    def _apply_policy_projection(
        initiative: Initiative,
        decision: PolicyDecision,
    ) -> None:
        """Project the latest deterministic policy result onto the initiative."""
        initiative.risk_score = decision.score
        initiative.risk_tier = decision.tier
        initiative.policy_id = decision.policy_id
        initiative.policy_version = decision.policy_version
        initiative.required_documents = decision.required_documents

    @staticmethod
    def _find_approval(initiative: Initiative, approval_id: str) -> Approval:
        """Return a gate owned by the initiative or raise not found."""
        approval = next((item for item in initiative.approvals if item.id == approval_id), None)
        if approval is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Approval not found")
        return approval

    @staticmethod
    def _current_submission(initiative: Initiative) -> ReviewSubmission:
        """Return the immutable submission for the current round."""
        submission = next(
            (
                item
                for item in initiative.review_submissions
                if item.review_round == initiative.current_review_round
            ),
            None,
        )
        if submission is None:
            raise ApplicationError(ErrorKind.CONFLICT, "Review submission history is missing")
        return submission

    @staticmethod
    def _reopen_assessments(
        assessments: list[Assessment],
        occurred_at: datetime,
    ) -> list[Assessment]:
        """Create editable current versions while preserving submitted snapshots."""
        reopened: list[Assessment] = []
        for assessment in assessments:
            if assessment.status is EntityStatus.UNDER_REVIEW:
                assessment.status = EntityStatus.DRAFT
                assessment.version += 1
                assessment.updated_at = occurred_at
                reopened.append(assessment)
        return reopened

    @staticmethod
    def _require_assessments_ready(
        assessments: list[Assessment],
        required_documents: list[str],
    ) -> None:
        """Require every structured policy document to be submitted for review."""
        structured_documents = {
            "ai-impact-assessment",
            "ripd",
            "international-processing-assessment",
        }
        required = set(required_documents) & structured_documents
        ready = {
            item.assessment_type for item in assessments if item.status is EntityStatus.UNDER_REVIEW
        }
        blocking = sorted(required - ready)
        if blocking:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                {
                    "message": "Assessments must be resubmitted before the initiative",
                    "blocking_assessments": blocking,
                },
            )

    @staticmethod
    def _review_state(initiative: Initiative) -> InitiativeReviewState:
        """Map ORM state into the framework-independent review domain."""
        return InitiativeReviewState(
            owner_id=initiative.business_owner_id,
            status=initiative.status,
            risk_tier=initiative.risk_tier,
            version=initiative.version,
            current_round=initiative.current_review_round,
            gates=tuple(
                ReviewGateState(
                    id=item.id,
                    area=item.area,
                    required=item.required,
                    status=item.status,
                    review_round=item.review_round,
                    version=item.version,
                    decided_by=item.decided_by,
                )
                for item in initiative.approvals
            ),
        )

    @staticmethod
    def _review_actor(principal: Principal) -> ReviewActor:
        """Map the authenticated transport principal into the review domain."""
        return ReviewActor(
            user_id=principal.user_id,
            approval_areas=principal.approval_areas,
            is_admin=principal.is_admin,
        )

    @staticmethod
    def _initiative_snapshot(initiative: Initiative) -> dict[str, object]:
        """Return the complete submitted proposal without ORM-internal fields."""
        return {
            "name": initiative.name,
            "description": initiative.description,
            "business_owner_id": initiative.business_owner_id,
            "business_area": initiative.business_area,
            "intended_users": initiative.intended_users,
            "decision_impact": initiative.decision_impact.value,
            "data_classification": initiative.data_classification.value,
            "autonomy_level": initiative.autonomy_level.value,
            "hosting_model": initiative.hosting_model.value,
            "affects_rights": initiative.affects_rights,
            "executes_actions": initiative.executes_actions,
            "personal_data": initiative.personal_data,
            "sensitive_data": initiative.sensitive_data,
            "children_data": initiative.children_data,
            "external_facing": initiative.external_facing,
            "regulated_context": initiative.regulated_context,
            "international_processing": initiative.international_processing,
            "inference_countries": list(initiative.inference_countries),
            "uses_rag": initiative.uses_rag,
            "uses_agents": initiative.uses_agents,
            "uses_mcp": initiative.uses_mcp,
            "uses_custom_model": initiative.uses_custom_model,
        }

    @staticmethod
    def _assessment_snapshots(assessments: list[Assessment]) -> list[dict[str, object]]:
        """Copy structured assessment versions into immutable review evidence."""
        return [
            {
                "id": item.id,
                "assessment_type": item.assessment_type,
                "schema_version": item.schema_version,
                "status": item.status.value,
                "answers": copy.deepcopy(item.answers),
                "risk_score": item.risk_score,
                "risk_tier": item.risk_tier.value if item.risk_tier else None,
                "assessed_by": item.assessed_by,
                "version": item.version,
            }
            for item in assessments
        ]

    @staticmethod
    def _evidence_digest(
        approval_id: str,
        principal_id: str,
        request: ApprovalDecisionRequest,
    ) -> str:
        """Bind a human attestation reference to actor, decision, and gate."""
        evidence = f"{approval_id}:{principal_id}:{request.evidence_uri}:{request.comments}"
        return hashlib.sha256(evidence.encode()).hexdigest()

    @staticmethod
    def _raise_review_error(error: ReviewConflict | ReviewForbidden) -> NoReturn:
        """Translate pure-domain errors into stable application categories."""
        if isinstance(error, ReviewForbidden):
            raise ApplicationError(ErrorKind.FORBIDDEN, str(error)) from error
        raise ApplicationError(ErrorKind.CONFLICT, str(error)) from error

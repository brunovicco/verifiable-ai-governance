import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from governance_schemas import (
    ApprovalStatus,
    EntityStatus,
    PolicyContext,
    RiskTier,
)
from policy_engine import GovernancePolicyEngine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_governance_api.audit import append_audit_event
from ai_governance_api.auth import Principal, get_principal
from ai_governance_api.database import get_db
from ai_governance_api.models import Approval, AuditEvent, Evidence, Initiative
from ai_governance_api.schemas import (
    ApprovalDecisionRequest,
    AuditEventRead,
    InitiativeCreate,
    InitiativeDetail,
    InitiativeRead,
    SubmissionRequest,
)

router = APIRouter(prefix="/api/v1/initiatives", tags=["initiatives"])
policy_engine = GovernancePolicyEngine()
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


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


async def _load_initiative(session: AsyncSession, initiative_id: str) -> Initiative:
    initiative = await session.scalar(
        select(Initiative)
        .where(Initiative.id == initiative_id)
        .options(selectinload(Initiative.approvals), selectinload(Initiative.systems))
    )
    if initiative is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Initiative not found")
    return initiative


@router.post("", response_model=InitiativeDetail, status_code=status.HTTP_201_CREATED)
async def create_initiative(
    request: InitiativeCreate,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Initiative:
    decision = policy_engine.evaluate(_policy_context(request))
    initiative = Initiative(
        **request.model_dump(),
        business_owner_id=principal.user_id,
        risk_score=decision.score,
        risk_tier=decision.tier,
        policy_id=decision.policy_id,
        policy_version=decision.policy_version,
        required_documents=decision.required_documents,
    )
    session.add(initiative)
    await session.flush()
    await append_audit_event(
        session,
        actor_id=principal.user_id,
        action="initiative.created",
        entity_type="initiative",
        entity_id=initiative.id,
        entity_version=initiative.version,
        payload={"risk_score": decision.score, "risk_tier": decision.tier.value},
    )
    await session.commit()
    return await _load_initiative(session, initiative.id)


@router.get("", response_model=list[InitiativeRead])
async def list_initiatives(
    session: DatabaseSession,
    _: CurrentPrincipal,
) -> list[Initiative]:
    result = await session.scalars(select(Initiative).order_by(Initiative.created_at.desc()))
    return list(result)


@router.get("/{initiative_id}", response_model=InitiativeDetail)
async def get_initiative(
    initiative_id: str,
    session: DatabaseSession,
    _: CurrentPrincipal,
) -> Initiative:
    return await _load_initiative(session, initiative_id)


@router.post("/{initiative_id}/submit", response_model=InitiativeDetail)
async def submit_initiative(
    initiative_id: str,
    request: SubmissionRequest,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Initiative:
    initiative = await _load_initiative(session, initiative_id)
    if initiative.business_owner_id != principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can submit"
        )
    if initiative.status is not EntityStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Initiative is not a draft"
        )
    if initiative.version != request.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version conflict")

    decision = policy_engine.evaluate(_policy_context(initiative))
    if not decision.can_submit:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "Policy blocked submission", "reasons": decision.blocked_reasons},
        )
    if initiative.approvals:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Approval gates already exist"
        )

    now = datetime.now(UTC)
    for requirement in decision.approvals:
        initiative.approvals.append(
            Approval(
                area=requirement.area,
                required=requirement.required,
                reason=requirement.reason,
                status=(
                    ApprovalStatus.PENDING if requirement.required else ApprovalStatus.NOT_REQUIRED
                ),
                requested_at=now if requirement.required else None,
            )
        )
    initiative.status = EntityStatus.UNDER_REVIEW
    initiative.submitted_at = now
    initiative.version += 1
    initiative.risk_score = decision.score
    initiative.risk_tier = decision.tier
    initiative.policy_id = decision.policy_id
    initiative.policy_version = decision.policy_version
    initiative.required_documents = decision.required_documents
    await session.flush()
    await append_audit_event(
        session,
        actor_id=principal.user_id,
        action="initiative.submitted",
        entity_type="initiative",
        entity_id=initiative.id,
        entity_version=initiative.version,
        payload={
            "policy_id": decision.policy_id,
            "policy_version": decision.policy_version,
            "required_approvals": [item.area.value for item in decision.approvals if item.required],
            "required_documents": decision.required_documents,
        },
    )
    await session.commit()
    return await _load_initiative(session, initiative.id)


@router.post("/{initiative_id}/approvals/{approval_id}/decision", response_model=InitiativeDetail)
async def decide_approval(
    initiative_id: str,
    approval_id: str,
    request: ApprovalDecisionRequest,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Initiative:
    initiative = await _load_initiative(session, initiative_id)
    approval = next((item for item in initiative.approvals if item.id == approval_id), None)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
    if not approval.required or approval.status is not ApprovalStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval is not pending")
    if approval.version != request.expected_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version conflict")
    if initiative.business_owner_id == principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Segregation of duties prevents owner self-approval",
        )
    if approval.area not in principal.approval_areas and not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Principal cannot approve for {approval.area.value}",
        )
    if initiative.risk_tier in {RiskTier.HIGH, RiskTier.CRITICAL} and any(
        item.decided_by == principal.user_id for item in initiative.approvals
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="High-risk gates require independent approvers across areas",
        )

    approval.status = request.decision
    approval.comments = request.comments
    approval.decided_by = principal.user_id
    approval.decided_at = datetime.now(UTC)
    approval.version += 1
    evidence_digest = hashlib.sha256(
        f"{approval.id}:{principal.user_id}:{request.evidence_uri}:{request.comments}".encode()
    ).hexdigest()
    session.add(
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

    required = [item for item in initiative.approvals if item.required]
    if any(item.status is ApprovalStatus.REJECTED for item in required):
        initiative.status = EntityStatus.REJECTED
    elif all(item.status is ApprovalStatus.APPROVED for item in required):
        initiative.status = EntityStatus.APPROVED
    else:
        initiative.status = EntityStatus.UNDER_REVIEW
    initiative.version += 1

    await session.flush()
    await append_audit_event(
        session,
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
    await session.commit()
    return await _load_initiative(session, initiative.id)


@router.get("/{initiative_id}/audit", response_model=list[AuditEventRead])
async def list_audit_events(
    initiative_id: str,
    session: DatabaseSession,
    _: CurrentPrincipal,
) -> list[AuditEvent]:
    await _load_initiative(session, initiative_id)
    events = await session.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_id == initiative_id)
        .order_by(AuditEvent.occurred_at)
    )
    return list(events)

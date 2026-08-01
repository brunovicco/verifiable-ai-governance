"""HTTP adapter for initiative lifecycle use cases."""

from fastapi import APIRouter, status

from ai_governance_api.dependencies import CurrentPrincipal, InitiativeServiceDependency
from ai_governance_api.models import AuditEvent, Initiative, ReviewSubmission
from ai_governance_api.schemas import (
    ApprovalDecisionRequest,
    AuditEventRead,
    InitiativeCreate,
    InitiativeDetail,
    InitiativeRead,
    InitiativeResubmissionRequest,
    InitiativeRevisionRequest,
    ReviewSubmissionRead,
    SubmissionRequest,
)

router = APIRouter(prefix="/api/v1/initiatives", tags=["initiatives"])


@router.post("", response_model=InitiativeDetail, status_code=status.HTTP_201_CREATED)
async def create_initiative(
    request: InitiativeCreate,
    service: InitiativeServiceDependency,
    principal: CurrentPrincipal,
) -> Initiative:
    """Create a governed initiative owned by the current principal."""
    return await service.create(request, principal)


@router.get("", response_model=list[InitiativeRead])
async def list_initiatives(
    service: InitiativeServiceDependency,
    _: CurrentPrincipal,
) -> list[Initiative]:
    """List initiatives visible to authenticated users."""
    return await service.list_initiatives()


@router.get("/{initiative_id}", response_model=InitiativeDetail)
async def get_initiative(
    initiative_id: str,
    service: InitiativeServiceDependency,
    _: CurrentPrincipal,
) -> Initiative:
    """Return a single initiative aggregate."""
    return await service.get(initiative_id)


@router.post("/{initiative_id}/submit", response_model=InitiativeDetail)
async def submit_initiative(
    initiative_id: str,
    request: SubmissionRequest,
    service: InitiativeServiceDependency,
    principal: CurrentPrincipal,
) -> Initiative:
    """Submit a draft initiative for policy-driven approval."""
    return await service.submit(initiative_id, request, principal)


@router.post("/{initiative_id}/resubmit", response_model=InitiativeDetail)
async def resubmit_initiative(
    initiative_id: str,
    request: InitiativeResubmissionRequest,
    service: InitiativeServiceDependency,
    principal: CurrentPrincipal,
) -> Initiative:
    """Apply owner revisions and create a new review round."""
    return await service.resubmit(initiative_id, request, principal)


@router.put("/{initiative_id}/revision", response_model=InitiativeDetail)
async def revise_initiative(
    initiative_id: str,
    request: InitiativeRevisionRequest,
    service: InitiativeServiceDependency,
    principal: CurrentPrincipal,
) -> Initiative:
    """Save owner corrections and recalculate policy before resubmission."""
    return await service.revise(initiative_id, request, principal)


@router.post("/{initiative_id}/approvals/{approval_id}/decision", response_model=InitiativeDetail)
async def decide_approval(
    initiative_id: str,
    approval_id: str,
    request: ApprovalDecisionRequest,
    service: InitiativeServiceDependency,
    principal: CurrentPrincipal,
) -> Initiative:
    """Record an authorized approval decision."""
    return await service.decide_approval(initiative_id, approval_id, request, principal)


@router.get("/{initiative_id}/review-history", response_model=list[ReviewSubmissionRead])
async def list_review_history(
    initiative_id: str,
    service: InitiativeServiceDependency,
    principal: CurrentPrincipal,
) -> list[ReviewSubmission]:
    """Return immutable review-round summaries to authorized participants."""
    return await service.list_review_history(initiative_id, principal)


@router.get("/{initiative_id}/audit", response_model=list[AuditEventRead])
async def list_audit_events(
    initiative_id: str,
    service: InitiativeServiceDependency,
    _: CurrentPrincipal,
) -> list[AuditEvent]:
    """Return the verifiable audit trail for an initiative."""
    return await service.list_audit_events(initiative_id)

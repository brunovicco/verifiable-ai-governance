"""FastAPI adapter for structured assessment use cases."""

from fastapi import APIRouter

from ai_governance_api.assessment_schemas import (
    AssessmentRead,
    AssessmentSubmitRequest,
    AssessmentWriteRequest,
    to_domain_answers,
)
from ai_governance_api.dependencies import (
    CurrentPrincipal,
    ListAssessmentsDependency,
    SaveAssessmentDependency,
    SubmitAssessmentDependency,
)
from ai_governance_api.domain import AssessmentActor, AssessmentKind

router = APIRouter(prefix="/api/v1", tags=["assessments"])


@router.get(
    "/initiatives/{initiative_id}/assessments",
    response_model=list[AssessmentRead],
)
async def list_assessments(
    initiative_id: str,
    use_case: ListAssessmentsDependency,
    _: CurrentPrincipal,
) -> list[AssessmentRead]:
    """List structured assessments associated with an initiative."""
    records = await use_case.execute(initiative_id)
    return [AssessmentRead.from_domain(record) for record in records]


@router.put(
    "/initiatives/{initiative_id}/assessments/{kind}",
    response_model=AssessmentRead,
)
async def save_assessment(
    initiative_id: str,
    kind: AssessmentKind,
    request: AssessmentWriteRequest,
    use_case: SaveAssessmentDependency,
    principal: CurrentPrincipal,
) -> AssessmentRead:
    """Create or update one definition-specific assessment draft."""
    record = await use_case.execute(
        initiative_id=initiative_id,
        kind=kind,
        answers=to_domain_answers(request.answers),
        actor=AssessmentActor(user_id=principal.user_id, is_admin=principal.is_admin),
        expected_version=request.expected_version,
    )
    return AssessmentRead.from_domain(record)


@router.post("/assessments/{assessment_id}/submit", response_model=AssessmentRead)
async def submit_assessment(
    assessment_id: str,
    request: AssessmentSubmitRequest,
    use_case: SubmitAssessmentDependency,
    principal: CurrentPrincipal,
) -> AssessmentRead:
    """Submit a complete draft assessment for independent review."""
    record = await use_case.execute(
        assessment_id=assessment_id,
        expected_version=request.expected_version,
        actor=AssessmentActor(user_id=principal.user_id, is_admin=principal.is_admin),
    )
    return AssessmentRead.from_domain(record)

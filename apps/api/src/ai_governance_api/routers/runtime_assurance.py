"""HTTP adapter for deterministic runtime assurance over sanitized telemetry."""

from fastapi import APIRouter, status

from ai_governance_api.dependencies import (
    CurrentAuthorizedPrincipal,
    CurrentPrincipal,
    RuntimeAssuranceActuationDecisionServiceDependency,
    RuntimeAssuranceActuationExecutionServiceDependency,
    RuntimeAssuranceActuationRequestServiceDependency,
    RuntimeAssuranceIncidentPromotionServiceDependency,
    RuntimeAssuranceResponseServiceDependency,
    RuntimeAssuranceRestoreDecisionServiceDependency,
    RuntimeAssuranceRestoreExecutionServiceDependency,
    RuntimeAssuranceRestoreRequestServiceDependency,
    RuntimeAssuranceServiceDependency,
)
from ai_governance_api.runtime_assurance_actuation_decision_schemas import (
    RuntimeAssuranceActuationDecisionCreate,
    RuntimeAssuranceActuationDecisionRead,
)
from ai_governance_api.runtime_assurance_actuation_execution_schemas import (
    RuntimeAssuranceActuationExecutionCreate,
    RuntimeAssuranceActuationExecutionRead,
)
from ai_governance_api.runtime_assurance_actuation_schemas import (
    RuntimeAssuranceActuationRequestCreate,
    RuntimeAssuranceActuationRequestRead,
)
from ai_governance_api.runtime_assurance_restore_schemas import (
    RuntimeAssuranceRestoreDecisionCreate,
    RuntimeAssuranceRestoreDecisionRead,
    RuntimeAssuranceRestoreExecutionCreate,
    RuntimeAssuranceRestoreExecutionRead,
    RuntimeAssuranceRestoreRequestCreate,
    RuntimeAssuranceRestoreRequestRead,
)
from ai_governance_api.runtime_assurance_schemas import (
    RuntimeAssuranceEvaluationRead,
    RuntimeAssuranceIncidentPromotionRead,
    RuntimeAssuranceIncidentPromotionRequest,
    RuntimeAssurancePolicyRead,
    RuntimeAssurancePolicyUpsertRequest,
    RuntimeAssuranceResponseRecommendationRead,
    RuntimeAssuranceResponseRecommendationRequest,
)

router = APIRouter(prefix="/api/v1", tags=["runtime-assurance"])


@router.put(
    "/agents/{agent_id}/runtime-assurance-policy",
    response_model=RuntimeAssurancePolicyRead,
)
async def put_runtime_assurance_policy(
    agent_id: str,
    request: RuntimeAssurancePolicyUpsertRequest,
    service: RuntimeAssuranceServiceDependency,
    principal: CurrentPrincipal,
) -> RuntimeAssurancePolicyRead:
    """Create or update one Agent assurance policy under optimistic concurrency."""
    policy = await service.put_policy(
        agent_id=agent_id,
        enabled=request.enabled,
        lookback_seconds=request.lookback_seconds,
        evaluation_sample_size=request.evaluation_sample_size,
        minimum_samples=request.minimum_samples,
        max_failure_rate=request.max_failure_rate,
        max_p95_duration_ms=request.max_p95_duration_ms,
        max_consecutive_failures=request.max_consecutive_failures,
        breach_severity=request.breach_severity,
        expected_version=request.expected_version,
        principal=principal,
    )
    return RuntimeAssurancePolicyRead.from_domain(policy)


@router.get(
    "/agents/{agent_id}/runtime-assurance-policy",
    response_model=RuntimeAssurancePolicyRead,
)
async def get_runtime_assurance_policy(
    agent_id: str,
    service: RuntimeAssuranceServiceDependency,
    principal: CurrentPrincipal,
) -> RuntimeAssurancePolicyRead:
    """Return the current assurance policy visible to an authorized stakeholder."""
    policy = await service.get_policy(agent_id=agent_id, principal=principal)
    return RuntimeAssurancePolicyRead.from_domain(policy)


@router.post(
    "/agents/{agent_id}/runtime-assurance-evaluations",
    response_model=RuntimeAssuranceEvaluationRead,
    status_code=status.HTTP_201_CREATED,
)
async def evaluate_runtime_assurance(
    agent_id: str,
    service: RuntimeAssuranceServiceDependency,
    principal: CurrentPrincipal,
) -> RuntimeAssuranceEvaluationRead:
    """Evaluate the bounded terminal-telemetry window and persist evidence."""
    evaluation = await service.evaluate(agent_id=agent_id, principal=principal)
    return RuntimeAssuranceEvaluationRead.from_domain(evaluation)


@router.get(
    "/agents/{agent_id}/runtime-assurance-evaluations",
    response_model=list[RuntimeAssuranceEvaluationRead],
)
async def list_runtime_assurance_evaluations(
    agent_id: str,
    service: RuntimeAssuranceServiceDependency,
    principal: CurrentPrincipal,
) -> list[RuntimeAssuranceEvaluationRead]:
    """List recent deterministic assurance evidence."""
    evaluations = await service.list_evaluations(
        agent_id=agent_id,
        principal=principal,
    )
    return [RuntimeAssuranceEvaluationRead.from_domain(evaluation) for evaluation in evaluations]


@router.post(
    "/runtime-assurance-evaluations/{evaluation_id}/incident-promotion",
    response_model=RuntimeAssuranceIncidentPromotionRead,
    status_code=status.HTTP_200_OK,
)
async def promote_runtime_assurance_incident(
    evaluation_id: str,
    request: RuntimeAssuranceIncidentPromotionRequest,
    service: RuntimeAssuranceIncidentPromotionServiceDependency,
    principal: CurrentPrincipal,
) -> RuntimeAssuranceIncidentPromotionRead:
    """Explicitly promote breached assurance evidence into incident lifecycle."""
    del request
    result = await service.promote(
        evaluation_id=evaluation_id,
        principal=principal,
    )
    return RuntimeAssuranceIncidentPromotionRead.from_domain(result)


@router.get(
    "/runtime-assurance-evaluations/{evaluation_id}/incident-promotion",
    response_model=RuntimeAssuranceIncidentPromotionRead,
)
async def get_runtime_assurance_incident_promotion(
    evaluation_id: str,
    service: RuntimeAssuranceIncidentPromotionServiceDependency,
    principal: CurrentPrincipal,
) -> RuntimeAssuranceIncidentPromotionRead:
    """Return persisted promotion lineage and current linked incident state."""
    result = await service.get_promotion(
        evaluation_id=evaluation_id,
        principal=principal,
    )
    return RuntimeAssuranceIncidentPromotionRead.from_domain(result)


@router.post(
    "/runtime-assurance-incident-promotions/{promotion_id}/response-recommendations",
    response_model=RuntimeAssuranceResponseRecommendationRead,
    status_code=status.HTTP_200_OK,
)
async def generate_runtime_assurance_response_recommendation(
    promotion_id: str,
    request: RuntimeAssuranceResponseRecommendationRequest,
    service: RuntimeAssuranceResponseServiceDependency,
    principal: CurrentPrincipal,
) -> RuntimeAssuranceResponseRecommendationRead:
    """Generate or replay deterministic advisory runtime-response evidence."""
    del request
    recommendation = await service.generate(
        promotion_id=promotion_id,
        principal=principal,
    )
    return RuntimeAssuranceResponseRecommendationRead.from_domain(recommendation)


@router.get(
    "/runtime-assurance-incident-promotions/{promotion_id}/response-recommendations",
    response_model=RuntimeAssuranceResponseRecommendationRead,
)
async def get_runtime_assurance_response_recommendation(
    promotion_id: str,
    service: RuntimeAssuranceResponseServiceDependency,
    principal: CurrentPrincipal,
) -> RuntimeAssuranceResponseRecommendationRead:
    """Return persisted deterministic advisory response evidence."""
    recommendation = await service.get(
        promotion_id=promotion_id,
        principal=principal,
    )
    return RuntimeAssuranceResponseRecommendationRead.from_domain(recommendation)


@router.post(
    "/runtime-assurance-response-recommendations/{recommendation_id}/actuation-request",
    response_model=RuntimeAssuranceActuationRequestRead,
    status_code=status.HTTP_200_OK,
)
async def create_runtime_assurance_actuation_request(
    recommendation_id: str,
    request: RuntimeAssuranceActuationRequestCreate,
    service: RuntimeAssuranceActuationRequestServiceDependency,
    principal: CurrentPrincipal,
) -> RuntimeAssuranceActuationRequestRead:
    """Create or replay one governed pending actuation approval request."""
    del request
    result = await service.create(
        recommendation_id=recommendation_id,
        principal=principal,
    )
    return RuntimeAssuranceActuationRequestRead.from_domain(result)


@router.get(
    "/runtime-assurance-response-recommendations/{recommendation_id}/actuation-request",
    response_model=RuntimeAssuranceActuationRequestRead,
)
async def get_runtime_assurance_actuation_request(
    recommendation_id: str,
    service: RuntimeAssuranceActuationRequestServiceDependency,
    principal: CurrentPrincipal,
) -> RuntimeAssuranceActuationRequestRead:
    """Return immutable governed actuation-request genesis evidence."""
    result = await service.get(
        recommendation_id=recommendation_id,
        principal=principal,
    )
    return RuntimeAssuranceActuationRequestRead.from_domain(result)


@router.post(
    "/runtime-assurance-actuation-requests/{request_id}/decision",
    response_model=RuntimeAssuranceActuationDecisionRead,
    status_code=status.HTTP_200_OK,
)
async def decide_runtime_assurance_actuation_request(
    request_id: str,
    request: RuntimeAssuranceActuationDecisionCreate,
    service: RuntimeAssuranceActuationDecisionServiceDependency,
    principal: CurrentAuthorizedPrincipal,
) -> RuntimeAssuranceActuationDecisionRead:
    """Record or replay one independent terminal human actuation decision."""
    result = await service.decide(
        request_id=request_id,
        decision=request.decision,
        reason=request.reason,
        principal=principal,
    )
    return RuntimeAssuranceActuationDecisionRead.from_domain(result)


@router.get(
    "/runtime-assurance-actuation-requests/{request_id}/decision",
    response_model=RuntimeAssuranceActuationDecisionRead,
)
async def get_runtime_assurance_actuation_decision(
    request_id: str,
    service: RuntimeAssuranceActuationDecisionServiceDependency,
    principal: CurrentAuthorizedPrincipal,
) -> RuntimeAssuranceActuationDecisionRead:
    """Return immutable terminal human decision evidence for one actuation request."""
    result = await service.get(
        request_id=request_id,
        principal=principal,
    )
    return RuntimeAssuranceActuationDecisionRead.from_domain(result)


@router.post(
    "/runtime-assurance-actuation-decisions/{decision_id}/execution",
    response_model=RuntimeAssuranceActuationExecutionRead,
    status_code=status.HTTP_200_OK,
)
async def execute_runtime_assurance_actuation_decision(
    decision_id: str,
    request: RuntimeAssuranceActuationExecutionCreate,
    service: RuntimeAssuranceActuationExecutionServiceDependency,
    principal: CurrentAuthorizedPrincipal,
) -> RuntimeAssuranceActuationExecutionRead:
    """Execute or recover one approved governed Runtime Control action."""
    del request
    result = await service.execute(
        decision_id=decision_id,
        principal=principal,
    )
    return RuntimeAssuranceActuationExecutionRead.from_domain(result)


@router.get(
    "/runtime-assurance-actuation-decisions/{decision_id}/execution",
    response_model=RuntimeAssuranceActuationExecutionRead,
)
async def get_runtime_assurance_actuation_execution(
    decision_id: str,
    service: RuntimeAssuranceActuationExecutionServiceDependency,
    principal: CurrentAuthorizedPrincipal,
) -> RuntimeAssuranceActuationExecutionRead:
    """Return immutable evidence for an applied governed Runtime Control action."""
    result = await service.get(
        decision_id=decision_id,
        principal=principal,
    )
    return RuntimeAssuranceActuationExecutionRead.from_domain(result)


@router.post(
    "/runtime-assurance-actuation-executions/{execution_id}/restore-request",
    response_model=RuntimeAssuranceRestoreRequestRead,
    status_code=status.HTTP_200_OK,
)
async def create_runtime_assurance_restore_request(
    execution_id: str,
    request: RuntimeAssuranceRestoreRequestCreate,
    service: RuntimeAssuranceRestoreRequestServiceDependency,
    principal: CurrentAuthorizedPrincipal,
) -> RuntimeAssuranceRestoreRequestRead:
    """Create or replay restore intent from an applied governed engage execution."""
    del request
    result = await service.create(source_execution_id=execution_id, principal=principal)
    return RuntimeAssuranceRestoreRequestRead.from_domain(result)


@router.get(
    "/runtime-assurance-actuation-executions/{execution_id}/restore-request",
    response_model=RuntimeAssuranceRestoreRequestRead,
)
async def get_runtime_assurance_restore_request(
    execution_id: str,
    service: RuntimeAssuranceRestoreRequestServiceDependency,
    principal: CurrentAuthorizedPrincipal,
) -> RuntimeAssuranceRestoreRequestRead:
    """Return restore request evidence for the current remediation snapshot."""
    result = await service.get(source_execution_id=execution_id, principal=principal)
    return RuntimeAssuranceRestoreRequestRead.from_domain(result)


@router.post(
    "/runtime-assurance-restore-requests/{request_id}/decision",
    response_model=RuntimeAssuranceRestoreDecisionRead,
    status_code=status.HTTP_200_OK,
)
async def decide_runtime_assurance_restore_request(
    request_id: str,
    request: RuntimeAssuranceRestoreDecisionCreate,
    service: RuntimeAssuranceRestoreDecisionServiceDependency,
    principal: CurrentAuthorizedPrincipal,
) -> RuntimeAssuranceRestoreDecisionRead:
    """Record or replay independent Security approval/rejection for restore."""
    result = await service.decide(
        request_id=request_id,
        decision=request.decision,
        reason=request.reason,
        principal=principal,
    )
    return RuntimeAssuranceRestoreDecisionRead.from_domain(result)


@router.get(
    "/runtime-assurance-restore-requests/{request_id}/decision",
    response_model=RuntimeAssuranceRestoreDecisionRead,
)
async def get_runtime_assurance_restore_decision(
    request_id: str,
    service: RuntimeAssuranceRestoreDecisionServiceDependency,
    principal: CurrentAuthorizedPrincipal,
) -> RuntimeAssuranceRestoreDecisionRead:
    """Return immutable restore decision evidence."""
    result = await service.get(request_id=request_id, principal=principal)
    return RuntimeAssuranceRestoreDecisionRead.from_domain(result)


@router.post(
    "/runtime-assurance-restore-decisions/{decision_id}/execution",
    response_model=RuntimeAssuranceRestoreExecutionRead,
    status_code=status.HTTP_200_OK,
)
async def execute_runtime_assurance_restore_decision(
    decision_id: str,
    request: RuntimeAssuranceRestoreExecutionCreate,
    service: RuntimeAssuranceRestoreExecutionServiceDependency,
    principal: CurrentAuthorizedPrincipal,
) -> RuntimeAssuranceRestoreExecutionRead:
    """Execute or recover one approved kill-switch restoration."""
    del request
    result = await service.execute(decision_id=decision_id, principal=principal)
    return RuntimeAssuranceRestoreExecutionRead.from_domain(result)


@router.get(
    "/runtime-assurance-restore-decisions/{decision_id}/execution",
    response_model=RuntimeAssuranceRestoreExecutionRead,
)
async def get_runtime_assurance_restore_execution(
    decision_id: str,
    service: RuntimeAssuranceRestoreExecutionServiceDependency,
    principal: CurrentAuthorizedPrincipal,
) -> RuntimeAssuranceRestoreExecutionRead:
    """Return immutable evidence for an applied kill-switch restoration."""
    result = await service.get(decision_id=decision_id, principal=principal)
    return RuntimeAssuranceRestoreExecutionRead.from_domain(result)

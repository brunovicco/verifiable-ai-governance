"""HTTP adapter for deterministic runtime assurance over sanitized telemetry."""

from fastapi import APIRouter, status

from ai_governance_api.dependencies import (
    CurrentPrincipal,
    RuntimeAssuranceServiceDependency,
)
from ai_governance_api.runtime_assurance_schemas import (
    RuntimeAssuranceEvaluationRead,
    RuntimeAssurancePolicyRead,
    RuntimeAssurancePolicyUpsertRequest,
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

"""HTTP adapter for runtime model-routing enforcement."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ai_governance_api.dependencies import (
    CurrentPrincipal,
    ListModelRoutingDecisionsDependency,
    RequestModelRoutingDecisionDependency,
)
from ai_governance_api.domain.model_routing import (
    ModelRoutingDecisionRecord,
    RoutingEnforcementOutcome,
)
from ai_governance_api.routing_schemas import (
    ModelRoutingDecisionRead,
    ModelRoutingDecisionRequest,
)

router = APIRouter(prefix="/api/v1", tags=["model-routing"])


@router.post(
    "/agents/{agent_id}/routing-decisions",
    response_model=ModelRoutingDecisionRead,
    responses={
        422: {"model": ModelRoutingDecisionRead},
        503: {"model": ModelRoutingDecisionRead},
    },
)
async def request_model_routing_decision(
    agent_id: str,
    request: ModelRoutingDecisionRequest,
    use_case: RequestModelRoutingDecisionDependency,
    principal: CurrentPrincipal,
) -> ModelRoutingDecisionRead | JSONResponse:
    """Request and persist an enforceable model-routing decision."""
    record = await use_case.execute(
        agent_id=agent_id,
        command=request.to_command(),
        principal=principal,
    )
    response = _to_read(record)
    if record.outcome is RoutingEnforcementOutcome.ALLOWED:
        return response
    status_code = (
        503
        if record.outcome is RoutingEnforcementOutcome.DEPENDENCY_UNAVAILABLE
        else 422
    )
    return JSONResponse(status_code=status_code, content=response.model_dump(mode="json"))


@router.get(
    "/agents/{agent_id}/routing-decisions",
    response_model=list[ModelRoutingDecisionRead],
)
async def list_model_routing_decisions(
    agent_id: str,
    use_case: ListModelRoutingDecisionsDependency,
    principal: CurrentPrincipal,
) -> list[ModelRoutingDecisionRead]:
    """List durable model-routing evidence visible to agent stakeholders."""
    records = await use_case.execute(agent_id=agent_id, principal=principal)
    return [_to_read(record) for record in records]


def _to_read(record: ModelRoutingDecisionRecord) -> ModelRoutingDecisionRead:
    """Flatten a pure decision record into the public transport contract."""
    return ModelRoutingDecisionRead.model_validate(
        {
            "id": record.id,
            "ai_system_id": record.ai_system_id,
            "initiative_id": record.initiative_id,
            "agent_id": record.agent_id,
            "requested_by": record.requested_by,
            "requested_at": record.requested_at,
            "scope_digest": record.scope_digest,
            "workflow_id": record.command.workflow_id,
            "task_id": record.command.task_id,
            "workload": record.command.workload,
            "risk_level": record.risk_level.value,
            "data_classification": record.data_classification.value,
            "context_tokens_estimated": record.command.context_tokens_estimated,
            "max_output_tokens_estimated": record.command.max_output_tokens_estimated,
            "structured_output_required": record.command.structured_output_required,
            "max_latency_ms": record.command.max_latency_ms,
            "max_cost_usd": record.command.max_cost_usd,
            "outcome": record.outcome,
            "decision_source": record.decision_source,
            "router_decision_id": record.router_decision_id,
            "router_outcome": record.router_outcome,
            "decided_at": record.decided_at,
            "selected_model_group": record.selected_model_group,
            "rejected_model_group": record.rejected_model_group,
            "reason": record.reason,
            "reason_code": record.reason_code,
            "observed_value": record.observed_value,
            "required_value": record.required_value,
            "rejected_candidates": record.rejected_candidates,
            "policy_id": record.policy_id,
            "policy_version": record.policy_version,
            "policy_digest": record.policy_digest,
            "service_version": record.service_version,
            "environment": record.environment,
            "version": record.version,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
    )

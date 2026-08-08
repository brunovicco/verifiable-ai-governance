"""HTTP adapter for direct emergency runtime-control operations."""

from fastapi import APIRouter

from ai_governance_api.dependencies import CurrentPrincipal, RuntimeControlServiceDependency
from ai_governance_api.runtime_control_schemas import (
    RuntimeControlCommandRequest,
    RuntimeControlReconcileRead,
    RuntimeControlReconcileRequest,
    RuntimeControlTransitionRead,
)

router = APIRouter(prefix="/api/v1", tags=["runtime-control"])


@router.post(
    "/agents/{agent_id}/runtime-control/activate",
    response_model=RuntimeControlTransitionRead,
)
async def activate_runtime_control(
    agent_id: str,
    request: RuntimeControlCommandRequest,
    service: RuntimeControlServiceDependency,
    principal: CurrentPrincipal,
) -> RuntimeControlTransitionRead:
    """Trip one agent's kill switch without requiring a pre-existing incident."""
    result = await service.activate(
        agent_id=agent_id,
        expected_version=request.expected_version,
        reason=request.reason,
        incident_id=request.incident_id,
        evidence_reference=request.evidence_reference,
        principal=principal,
    )
    return RuntimeControlTransitionRead.from_domain(result)


@router.post(
    "/agents/{agent_id}/runtime-control/deactivate",
    response_model=RuntimeControlTransitionRead,
)
async def deactivate_runtime_control(
    agent_id: str,
    request: RuntimeControlCommandRequest,
    service: RuntimeControlServiceDependency,
    principal: CurrentPrincipal,
) -> RuntimeControlTransitionRead:
    """Restore one agent while preserving revocation of pre-restore authorizations."""
    result = await service.deactivate(
        agent_id=agent_id,
        expected_version=request.expected_version,
        reason=request.reason,
        incident_id=request.incident_id,
        evidence_reference=request.evidence_reference,
        principal=principal,
    )
    return RuntimeControlTransitionRead.from_domain(result)


@router.post(
    "/runtime-control/reconcile",
    response_model=RuntimeControlReconcileRead,
)
async def reconcile_runtime_control(
    request: RuntimeControlReconcileRequest,
    service: RuntimeControlServiceDependency,
    principal: CurrentPrincipal,
) -> RuntimeControlReconcileRead:
    """Allow an administrator to finish pending transitions after partial failures."""
    results = await service.reconcile_pending(principal=principal, limit=request.limit)
    return RuntimeControlReconcileRead(
        reconciled=[RuntimeControlTransitionRead.from_domain(result) for result in results]
    )

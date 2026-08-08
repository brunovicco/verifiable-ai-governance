"""HTTP adapter for incident, kill-switch, and temporary-exception management."""

from fastapi import APIRouter, status

from ai_governance_api.dependencies import (
    CurrentPrincipal,
    IncidentServiceDependency,
    RuntimeControlServiceDependency,
)
from ai_governance_api.incident_schemas import (
    AgentKillSwitchRead,
    ExceptionDecisionRequest,
    ExceptionRequestRequest,
    ExceptionRevokeRequest,
    IncidentCloseRequest,
    IncidentContainRequest,
    IncidentRead,
    IncidentReportRequest,
    KillSwitchRequest,
    PolicyExceptionRead,
    RemediationPlanRequest,
)

router = APIRouter(prefix="/api/v1", tags=["incidents"])


@router.post(
    "/systems/{system_id}/incidents",
    response_model=IncidentRead,
    status_code=status.HTTP_201_CREATED,
)
async def report_incident(
    system_id: str,
    request: IncidentReportRequest,
    service: IncidentServiceDependency,
    principal: CurrentPrincipal,
) -> IncidentRead:
    """Open a new incident for an AI system."""
    incident = await service.report_incident(
        ai_system_id=system_id,
        title=request.title,
        severity=request.severity,
        description=request.description,
        detected_at=request.detected_at,
        principal=principal,
    )
    return IncidentRead.from_domain(incident)


@router.get("/systems/{system_id}/incidents", response_model=list[IncidentRead])
async def list_incidents(
    system_id: str,
    service: IncidentServiceDependency,
    principal: CurrentPrincipal,
) -> list[IncidentRead]:
    """List incidents reported for an AI system."""
    incidents = await service.list_incidents(ai_system_id=system_id, principal=principal)
    return [IncidentRead.from_domain(incident) for incident in incidents]


@router.get("/incidents/{incident_id}", response_model=IncidentRead)
async def get_incident(
    incident_id: str,
    service: IncidentServiceDependency,
    principal: CurrentPrincipal,
) -> IncidentRead:
    """Return one incident's lifecycle and remediation plan."""
    incident = await service.get_incident(incident_id=incident_id, principal=principal)
    return IncidentRead.from_domain(incident)


@router.post("/incidents/{incident_id}/contain", response_model=IncidentRead)
async def contain_incident(
    incident_id: str,
    request: IncidentContainRequest,
    service: IncidentServiceDependency,
    principal: CurrentPrincipal,
) -> IncidentRead:
    """Record containment measures and move an open incident to contained."""
    incident = await service.contain_incident(
        incident_id=incident_id,
        containment=request.containment,
        expected_version=request.expected_version,
        principal=principal,
    )
    return IncidentRead.from_domain(incident)


@router.post("/incidents/{incident_id}/remediation-plan", response_model=IncidentRead)
async def set_remediation_plan(
    incident_id: str,
    request: RemediationPlanRequest,
    service: IncidentServiceDependency,
    principal: CurrentPrincipal,
) -> IncidentRead:
    """Record a remediation plan for an open or contained incident."""
    incident = await service.set_remediation_plan(
        incident_id=incident_id,
        remediation_owner_id=request.remediation_owner_id,
        remediation_description=request.remediation_description,
        remediation_due_at=request.remediation_due_at,
        expected_version=request.expected_version,
        principal=principal,
    )
    return IncidentRead.from_domain(incident)


@router.post("/incidents/{incident_id}/close", response_model=IncidentRead)
async def close_incident(
    incident_id: str,
    request: IncidentCloseRequest,
    service: IncidentServiceDependency,
    principal: CurrentPrincipal,
) -> IncidentRead:
    """Close an incident once its remediation plan is on record."""
    incident = await service.close_incident(
        incident_id=incident_id,
        expected_version=request.expected_version,
        principal=principal,
    )
    return IncidentRead.from_domain(incident)


@router.post(
    "/incidents/{incident_id}/agents/{agent_id}/kill-switch/engage",
    response_model=AgentKillSwitchRead,
)
async def engage_kill_switch(
    incident_id: str,
    agent_id: str,
    request: KillSwitchRequest,
    service: RuntimeControlServiceDependency,
    principal: CurrentPrincipal,
) -> AgentKillSwitchRead:
    """Trip an agent through the single monotonic Runtime Control write path."""
    result = await service.activate(
        incident_id=incident_id,
        agent_id=agent_id,
        expected_version=request.expected_version,
        reason=request.reason or f"Incident response containment: {incident_id}",
        principal=principal,
    )
    return AgentKillSwitchRead(
        id=result.agent_id,
        ai_system_id=result.ai_system_id,
        kill_switch_enabled=result.kill_switch_enabled,
        kill_switch_engaged=result.kill_switch_engaged,
        version=result.agent_version,
    )


@router.post(
    "/incidents/{incident_id}/agents/{agent_id}/kill-switch/restore",
    response_model=AgentKillSwitchRead,
)
async def restore_kill_switch(
    incident_id: str,
    agent_id: str,
    request: KillSwitchRequest,
    service: RuntimeControlServiceDependency,
    principal: CurrentPrincipal,
) -> AgentKillSwitchRead:
    """Restore an agent through the single monotonic Runtime Control write path."""
    result = await service.deactivate(
        incident_id=incident_id,
        agent_id=agent_id,
        expected_version=request.expected_version,
        reason=request.reason or f"Incident response restore: {incident_id}",
        principal=principal,
    )
    return AgentKillSwitchRead(
        id=result.agent_id,
        ai_system_id=result.ai_system_id,
        kill_switch_enabled=result.kill_switch_enabled,
        kill_switch_engaged=result.kill_switch_engaged,
        version=result.agent_version,
    )


@router.post(
    "/incidents/{incident_id}/exceptions",
    response_model=PolicyExceptionRead,
    status_code=status.HTTP_201_CREATED,
)
async def request_exception(
    incident_id: str,
    request: ExceptionRequestRequest,
    service: IncidentServiceDependency,
    principal: CurrentPrincipal,
) -> PolicyExceptionRead:
    """Request a temporary, expiring exception while an incident is active."""
    exception = await service.request_exception(
        incident_id=incident_id,
        purpose=request.purpose,
        scope_description=request.scope_description,
        compensating_controls=request.compensating_controls,
        expires_at=request.expires_at,
        principal=principal,
    )
    return PolicyExceptionRead.from_domain(exception, state=service.exception_state(exception))


@router.get("/incidents/{incident_id}/exceptions", response_model=list[PolicyExceptionRead])
async def list_exceptions(
    incident_id: str,
    service: IncidentServiceDependency,
    principal: CurrentPrincipal,
) -> list[PolicyExceptionRead]:
    """List temporary exceptions requested for one incident."""
    exceptions = await service.list_exceptions(incident_id=incident_id, principal=principal)
    return [
        PolicyExceptionRead.from_domain(exception, state=service.exception_state(exception))
        for exception in exceptions
    ]


@router.post("/exceptions/{exception_id}/decide", response_model=PolicyExceptionRead)
async def decide_exception(
    exception_id: str,
    request: ExceptionDecisionRequest,
    service: IncidentServiceDependency,
    principal: CurrentPrincipal,
) -> PolicyExceptionRead:
    """Approve or reject a pending exception, enforcing segregation of duties."""
    exception = await service.decide_exception(
        exception_id=exception_id,
        approved=request.approved,
        decision_reason=request.decision_reason,
        expected_version=request.expected_version,
        principal=principal,
    )
    return PolicyExceptionRead.from_domain(exception, state=service.exception_state(exception))


@router.post("/exceptions/{exception_id}/revoke", response_model=PolicyExceptionRead)
async def revoke_exception(
    exception_id: str,
    request: ExceptionRevokeRequest,
    service: IncidentServiceDependency,
    principal: CurrentPrincipal,
) -> PolicyExceptionRead:
    """Revoke a pending or approved exception ahead of its natural expiry."""
    exception = await service.revoke_exception(
        exception_id=exception_id,
        decision_reason=request.decision_reason,
        expected_version=request.expected_version,
        principal=principal,
    )
    return PolicyExceptionRead.from_domain(exception, state=service.exception_state(exception))

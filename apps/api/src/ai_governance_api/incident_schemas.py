"""HTTP schemas for incident, kill-switch, and temporary-exception management."""

from datetime import datetime

from governance_schemas import RiskTier
from pydantic import BaseModel, ConfigDict, Field

from ai_governance_api.domain.incidents import (
    AgentKillSwitchState,
    ExceptionState,
    ExceptionStatus,
    IncidentRecord,
    IncidentStatus,
    PolicyExceptionRecord,
)


class IncidentReportRequest(BaseModel):
    """Facts required to open a new incident."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=200)
    severity: RiskTier
    description: str = Field(min_length=1)
    detected_at: datetime


class IncidentContainRequest(BaseModel):
    """Containment measures recorded while moving an incident to contained."""

    model_config = ConfigDict(extra="forbid")

    containment: str = Field(min_length=1)
    expected_version: int


class RemediationPlanRequest(BaseModel):
    """Remediation plan recorded for an open or contained incident."""

    model_config = ConfigDict(extra="forbid")

    remediation_owner_id: str = Field(min_length=1, max_length=200)
    remediation_description: str = Field(min_length=1)
    remediation_due_at: datetime
    expected_version: int


class IncidentCloseRequest(BaseModel):
    """Optimistic-concurrency guard for closing an incident."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int


class KillSwitchRequest(BaseModel):
    """Optimistic-concurrency guard for a kill-switch action on one agent."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int


class IncidentRead(BaseModel):
    """Serialized incident lifecycle and remediation plan."""

    id: str
    ai_system_id: str
    title: str
    severity: RiskTier
    status: IncidentStatus
    description: str
    detected_at: datetime
    owner_id: str
    containment: str | None
    remediation_owner_id: str | None
    remediation_description: str | None
    remediation_due_at: datetime | None
    resolved_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, record: IncidentRecord) -> "IncidentRead":
        """Map the pure incident record into its public transport contract."""
        return cls(
            id=record.id,
            ai_system_id=record.ai_system_id,
            title=record.title,
            severity=record.severity,
            status=record.status,
            description=record.description,
            detected_at=record.detected_at,
            owner_id=record.owner_id,
            containment=record.containment,
            remediation_owner_id=record.remediation_owner_id,
            remediation_description=record.remediation_description,
            remediation_due_at=record.remediation_due_at,
            resolved_at=record.resolved_at,
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class AgentKillSwitchRead(BaseModel):
    """Serialized runtime kill-switch state for one agent."""

    id: str
    ai_system_id: str
    kill_switch_enabled: bool
    kill_switch_engaged: bool
    version: int

    @classmethod
    def from_domain(cls, state: AgentKillSwitchState) -> "AgentKillSwitchRead":
        """Map the pure kill-switch state into its public transport contract."""
        return cls(
            id=state.id,
            ai_system_id=state.ai_system_id,
            kill_switch_enabled=state.kill_switch_enabled,
            kill_switch_engaged=state.kill_switch_engaged,
            version=state.version,
        )


class ExceptionRequestRequest(BaseModel):
    """Facts required to request a temporary exception during an incident."""

    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=1)
    scope_description: str = Field(min_length=1)
    compensating_controls: str = Field(min_length=1)
    expires_at: datetime


class ExceptionDecisionRequest(BaseModel):
    """An administrator's approval or rejection of a pending exception."""

    model_config = ConfigDict(extra="forbid")

    approved: bool
    decision_reason: str | None = None
    expected_version: int


class ExceptionRevokeRequest(BaseModel):
    """An administrator's early revocation of an exception."""

    model_config = ConfigDict(extra="forbid")

    decision_reason: str | None = None
    expected_version: int


class PolicyExceptionRead(BaseModel):
    """Serialized temporary exception, including its computed validity."""

    id: str
    incident_id: str
    ai_system_id: str
    requested_by: str
    requested_at: datetime
    purpose: str
    scope_description: str
    compensating_controls: str
    expires_at: datetime
    status: ExceptionStatus
    state: ExceptionState
    decided_by: str | None
    decided_at: datetime | None
    decision_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(
        cls, record: PolicyExceptionRecord, *, state: ExceptionState
    ) -> "PolicyExceptionRead":
        """Map the pure exception record and its computed state into transport."""
        return cls(
            id=record.id,
            incident_id=record.incident_id,
            ai_system_id=record.ai_system_id,
            requested_by=record.requested_by,
            requested_at=record.requested_at,
            purpose=record.purpose,
            scope_description=record.scope_description,
            compensating_controls=record.compensating_controls,
            expires_at=record.expires_at,
            status=record.status,
            state=state,
            decided_by=record.decided_by,
            decided_at=record.decided_at,
            decision_reason=record.decision_reason,
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

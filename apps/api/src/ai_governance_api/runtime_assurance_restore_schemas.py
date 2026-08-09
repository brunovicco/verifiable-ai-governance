"""HTTP contracts for governed Runtime Assurance kill-switch restore evidence."""

from datetime import datetime

from governance_schemas import ApprovalArea
from pydantic import BaseModel, ConfigDict, Field

from ai_governance_api.domain.incidents import IncidentStatus
from ai_governance_api.domain.runtime_assurance_restore import (
    MAX_RUNTIME_ASSURANCE_RESTORE_REASON_LENGTH,
    RuntimeAssuranceRestoreAction,
    RuntimeAssuranceRestoreDecision,
    RuntimeAssuranceRestoreDecisionOutcome,
    RuntimeAssuranceRestoreExecution,
    RuntimeAssuranceRestoreRequest,
    RuntimeAssuranceRestoreRequestState,
)
from ai_governance_api.domain.runtime_control import RuntimeControlState


class RuntimeAssuranceRestoreRequestCreate(BaseModel):
    """Explicit empty command; source engagement and remediation are server-derived."""

    model_config = ConfigDict(extra="forbid")


class RuntimeAssuranceRestoreRequestRead(BaseModel):
    """Serialized immutable restore-request genesis evidence."""

    id: str
    schema_version: str
    source_execution_id: str
    source_execution_digest: str
    agent_id: str
    ai_system_id: str
    incident_id: str
    action: RuntimeAssuranceRestoreAction
    state: RuntimeAssuranceRestoreRequestState
    remediation_digest: str
    incident_status: IncidentStatus
    incident_version: int
    requested_by: str
    requested_at: datetime
    request_digest: str
    version: int

    @classmethod
    def from_domain(
        cls,
        request: RuntimeAssuranceRestoreRequest,
    ) -> "RuntimeAssuranceRestoreRequestRead":
        """Map immutable restore request evidence to its HTTP representation."""
        return cls(
            id=request.id,
            schema_version=request.schema_version,
            source_execution_id=request.source_execution_id,
            source_execution_digest=request.source_execution_digest,
            agent_id=request.agent_id,
            ai_system_id=request.ai_system_id,
            incident_id=request.incident_id,
            action=request.action,
            state=request.state,
            remediation_digest=request.remediation_digest,
            incident_status=request.incident_status,
            incident_version=request.incident_version,
            requested_by=request.requested_by,
            requested_at=request.requested_at,
            request_digest=request.request_digest,
            version=request.version,
        )


class RuntimeAssuranceRestoreDecisionCreate(BaseModel):
    """Closed human restore decision; identity and action are server-derived."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: RuntimeAssuranceRestoreDecisionOutcome
    reason: str = Field(min_length=1, max_length=MAX_RUNTIME_ASSURANCE_RESTORE_REASON_LENGTH)


class RuntimeAssuranceRestoreDecisionRead(BaseModel):
    """Serialized immutable restore approval/rejection evidence."""

    id: str
    schema_version: str
    request_id: str
    request_digest: str
    source_execution_id: str
    source_execution_digest: str
    action: RuntimeAssuranceRestoreAction
    decision: RuntimeAssuranceRestoreDecisionOutcome
    approval_area: ApprovalArea
    decided_by: str
    decided_at: datetime
    reason: str
    decision_digest: str
    version: int

    @classmethod
    def from_domain(
        cls,
        decision: RuntimeAssuranceRestoreDecision,
    ) -> "RuntimeAssuranceRestoreDecisionRead":
        """Map immutable restore decision evidence to its HTTP representation."""
        return cls(
            id=decision.id,
            schema_version=decision.schema_version,
            request_id=decision.request_id,
            request_digest=decision.request_digest,
            source_execution_id=decision.source_execution_id,
            source_execution_digest=decision.source_execution_digest,
            action=decision.action,
            decision=decision.decision,
            approval_area=decision.approval_area,
            decided_by=decision.decided_by,
            decided_at=decision.decided_at,
            reason=decision.reason,
            decision_digest=decision.decision_digest,
            version=decision.version,
        )


class RuntimeAssuranceRestoreExecutionCreate(BaseModel):
    """Explicit empty command; execution target and Runtime Control inputs are derived."""

    model_config = ConfigDict(extra="forbid")


class RuntimeAssuranceRestoreExecutionRead(BaseModel):
    """Serialized immutable applied restore execution receipt."""

    id: str
    schema_version: str
    decision_id: str
    decision_digest: str
    request_id: str
    request_digest: str
    source_execution_id: str
    source_execution_digest: str
    action: RuntimeAssuranceRestoreAction
    agent_id: str
    ai_system_id: str
    incident_id: str
    runtime_transition_id: str
    control_epoch: int
    previous_state: RuntimeControlState
    target_state: RuntimeControlState
    revoked_through_agent_version: int
    resulting_agent_version: int
    executed_by: str
    executed_at: datetime
    execution_digest: str
    version: int

    @classmethod
    def from_domain(
        cls,
        execution: RuntimeAssuranceRestoreExecution,
    ) -> "RuntimeAssuranceRestoreExecutionRead":
        """Map immutable restore execution evidence to its HTTP representation."""
        return cls(
            id=execution.id,
            schema_version=execution.schema_version,
            decision_id=execution.decision_id,
            decision_digest=execution.decision_digest,
            request_id=execution.request_id,
            request_digest=execution.request_digest,
            source_execution_id=execution.source_execution_id,
            source_execution_digest=execution.source_execution_digest,
            action=execution.action,
            agent_id=execution.agent_id,
            ai_system_id=execution.ai_system_id,
            incident_id=execution.incident_id,
            runtime_transition_id=execution.runtime_transition_id,
            control_epoch=execution.control_epoch,
            previous_state=execution.previous_state,
            target_state=execution.target_state,
            revoked_through_agent_version=execution.revoked_through_agent_version,
            resulting_agent_version=execution.resulting_agent_version,
            executed_by=execution.executed_by,
            executed_at=execution.executed_at,
            execution_digest=execution.execution_digest,
            version=execution.version,
        )

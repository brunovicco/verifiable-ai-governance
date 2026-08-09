"""HTTP contracts for governed Runtime Assurance actuation execution receipts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ai_governance_api.domain.runtime_assurance_actuation import RuntimeAssuranceActuationAction
from ai_governance_api.domain.runtime_assurance_actuation_executions import (
    RuntimeAssuranceActuationExecution,
)
from ai_governance_api.domain.runtime_control import RuntimeControlState


class RuntimeAssuranceActuationExecutionCreate(BaseModel):
    """Explicit empty command; execution identity and action are server-derived."""

    model_config = ConfigDict(extra="forbid")


class RuntimeAssuranceActuationExecutionRead(BaseModel):
    """Serialized immutable evidence for one applied governed Runtime Control action."""

    id: str
    schema_version: str
    decision_id: str
    decision_digest: str
    request_id: str
    request_digest: str
    action: RuntimeAssuranceActuationAction
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
        execution: RuntimeAssuranceActuationExecution,
    ) -> "RuntimeAssuranceActuationExecutionRead":
        """Map immutable applied execution evidence to its HTTP representation."""
        return cls(
            id=execution.id,
            schema_version=execution.schema_version,
            decision_id=execution.decision_id,
            decision_digest=execution.decision_digest,
            request_id=execution.request_id,
            request_digest=execution.request_digest,
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

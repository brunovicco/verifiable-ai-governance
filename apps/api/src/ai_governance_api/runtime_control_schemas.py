"""HTTP schemas for emergency runtime-control commands and reconciliation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ai_governance_api.domain.runtime_control import (
    RuntimeControlResult,
    RuntimeControlState,
    RuntimeControlTransitionStatus,
)


class RuntimeControlCommandRequest(BaseModel):
    """Operator intent for one activate/deactivate transition."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    incident_id: str | None = Field(default=None, min_length=1, max_length=36)
    evidence_reference: str | None = Field(default=None, min_length=1, max_length=500)


class RuntimeControlReconcileRequest(BaseModel):
    """Bounded administrative request to repair pending transitions."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=100, ge=1, le=1000)


class RuntimeControlTransitionRead(BaseModel):
    """Applied agent state and durable transition evidence."""

    transition_id: str
    agent_id: str
    ai_system_id: str
    control_epoch: int
    previous_state: RuntimeControlState
    target_state: RuntimeControlState
    status: RuntimeControlTransitionStatus
    revoked_through_agent_version: int
    reason: str
    requested_by: str
    requested_at: datetime
    applied_at: datetime | None
    incident_id: str | None
    evidence_reference: str | None
    kill_switch_enabled: bool
    kill_switch_engaged: bool
    agent_version: int

    @classmethod
    def from_domain(cls, result: RuntimeControlResult) -> "RuntimeControlTransitionRead":
        """Map the pure application result into the transport contract."""
        transition = result.transition
        return cls(
            transition_id=transition.id,
            agent_id=result.agent_id,
            ai_system_id=result.ai_system_id,
            control_epoch=transition.control_epoch,
            previous_state=transition.previous_state,
            target_state=transition.target_state,
            status=transition.status,
            revoked_through_agent_version=transition.revoked_through_agent_version,
            reason=transition.reason,
            requested_by=transition.requested_by,
            requested_at=transition.requested_at,
            applied_at=transition.applied_at,
            incident_id=transition.incident_id,
            evidence_reference=transition.evidence_reference,
            kill_switch_enabled=result.kill_switch_enabled,
            kill_switch_engaged=result.kill_switch_engaged,
            agent_version=result.agent_version,
        )


class RuntimeControlReconcileRead(BaseModel):
    """Transitions repaired by one bounded reconciliation command."""

    reconciled: list[RuntimeControlTransitionRead]

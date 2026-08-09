"""HTTP contracts for governed Runtime Assurance actuation decisions."""

from datetime import datetime

from governance_schemas import ApprovalArea
from pydantic import BaseModel, ConfigDict, Field

from ai_governance_api.domain.runtime_assurance_actuation import RuntimeAssuranceActuationAction
from ai_governance_api.domain.runtime_assurance_actuation_decisions import (
    MAX_ACTUATION_DECISION_REASON_LENGTH,
    RuntimeAssuranceActuationDecision,
    RuntimeAssuranceActuationDecisionOutcome,
)


class RuntimeAssuranceActuationDecisionCreate(BaseModel):
    """Closed human decision command; identity and governed action are server-derived."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: RuntimeAssuranceActuationDecisionOutcome
    reason: str = Field(min_length=1, max_length=MAX_ACTUATION_DECISION_REASON_LENGTH)


class RuntimeAssuranceActuationDecisionRead(BaseModel):
    """Serialized immutable human approval/rejection evidence."""

    id: str
    schema_version: str
    request_id: str
    request_digest: str
    action: RuntimeAssuranceActuationAction
    decision: RuntimeAssuranceActuationDecisionOutcome
    approval_area: ApprovalArea
    decided_by: str
    decided_at: datetime
    reason: str
    decision_digest: str
    version: int

    @classmethod
    def from_domain(
        cls,
        decision: RuntimeAssuranceActuationDecision,
    ) -> "RuntimeAssuranceActuationDecisionRead":
        """Map immutable decision evidence to its HTTP representation."""
        return cls(
            id=decision.id,
            schema_version=decision.schema_version,
            request_id=decision.request_id,
            request_digest=decision.request_digest,
            action=decision.action,
            decision=decision.decision,
            approval_area=decision.approval_area,
            decided_by=decision.decided_by,
            decided_at=decision.decided_at,
            reason=decision.reason,
            decision_digest=decision.decision_digest,
            version=decision.version,
        )

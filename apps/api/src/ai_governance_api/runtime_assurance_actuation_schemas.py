"""HTTP contracts for governed Runtime Assurance actuation approval requests."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ai_governance_api.domain.runtime_assurance_actuation import (
    RuntimeAssuranceActuationAction,
    RuntimeAssuranceActuationRequest,
    RuntimeAssuranceActuationRequestState,
)


class RuntimeAssuranceActuationRequestCreate(BaseModel):
    """Explicit empty command; all binding and action facts are server-derived."""

    model_config = ConfigDict(extra="forbid")


class RuntimeAssuranceActuationRequestRead(BaseModel):
    """Serialized immutable request genesis evidence."""

    id: str
    schema_version: str
    recommendation_id: str
    recommendation_digest: str
    promotion_id: str
    evaluation_id: str
    incident_id: str
    agent_id: str
    ai_system_id: str
    action: RuntimeAssuranceActuationAction
    state: RuntimeAssuranceActuationRequestState
    requested_by: str
    requested_at: datetime
    request_digest: str
    version: int

    @classmethod
    def from_domain(
        cls,
        request: RuntimeAssuranceActuationRequest,
    ) -> "RuntimeAssuranceActuationRequestRead":
        """Map immutable domain evidence to its HTTP representation."""
        return cls(
            id=request.id,
            schema_version=request.schema_version,
            recommendation_id=request.recommendation_id,
            recommendation_digest=request.recommendation_digest,
            promotion_id=request.promotion_id,
            evaluation_id=request.evaluation_id,
            incident_id=request.incident_id,
            agent_id=request.agent_id,
            ai_system_id=request.ai_system_id,
            action=request.action,
            state=request.state,
            requested_by=request.requested_by,
            requested_at=request.requested_at,
            request_digest=request.request_digest,
            version=request.version,
        )

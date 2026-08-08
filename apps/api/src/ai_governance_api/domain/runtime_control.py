"""Pure records and policies for emergency runtime kill-switch control."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ai_governance_api.domain.incidents import IncidentStatus


class RuntimeControlDomainError(ValueError):
    """Raised when a requested runtime-control transition is invalid."""


class RuntimeControlUnavailable(RuntimeError):
    """Raised when the runtime-control projection cannot be trusted."""


class RuntimeControlState(StrEnum):
    """Effective runtime execution state of one governed agent."""

    INACTIVE = "inactive"
    ACTIVE = "active"


class RuntimeControlTransitionStatus(StrEnum):
    """Durable lifecycle of one runtime-control transition."""

    PENDING = "pending"
    APPLIED = "applied"


@dataclass(frozen=True, slots=True)
class RuntimeControlAgentContext:
    """Trusted mutable agent facts required to authorize a transition."""

    agent_id: str
    ai_system_id: str
    ai_system_owner_id: str
    agent_owner_id: str
    kill_switch_enabled: bool
    kill_switch_engaged: bool
    agent_version: int

    @property
    def state(self) -> RuntimeControlState:
        """Return the state represented by the durable agent row."""
        return (
            RuntimeControlState.ACTIVE
            if self.kill_switch_engaged
            else RuntimeControlState.INACTIVE
        )


@dataclass(frozen=True, slots=True)
class RuntimeControlTransitionRecord:
    """Durable intent and completion evidence for one control-state change."""

    id: str
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
    version: int


@dataclass(frozen=True, slots=True)
class RuntimeControlSnapshot:
    """Minimal projection consumed by runtime enforcement components."""

    agent_id: str
    control_epoch: int
    state: RuntimeControlState
    revoked_through_agent_version: int
    transition_id: str | None
    schema_version: str = "1.0"


@dataclass(frozen=True, slots=True)
class RuntimeControlDurableState:
    """Authoritative DB state used to verify or repair the runtime projection."""

    snapshot: RuntimeControlSnapshot
    pending_transition_id: str | None
    durable_consistent: bool


@dataclass(frozen=True, slots=True)
class RuntimeControlResult:
    """Applied agent state together with the transition that produced it."""

    agent_id: str
    ai_system_id: str
    kill_switch_enabled: bool
    kill_switch_engaged: bool
    agent_version: int
    transition: RuntimeControlTransitionRecord


@dataclass(frozen=True, slots=True)
class RuntimeControlIncidentContext:
    """Optional incident facts preserved for legacy incident-bound commands."""

    incident_id: str
    status: IncidentStatus


def validate_transition(
    context: RuntimeControlAgentContext,
    *,
    target_state: RuntimeControlState,
    incident: RuntimeControlIncidentContext | None,
) -> None:
    """Validate state-machine invariants without performing I/O."""
    if not context.kill_switch_enabled:
        raise RuntimeControlDomainError("Agent does not declare an available kill switch")
    if target_state is context.state:
        if target_state is RuntimeControlState.ACTIVE:
            raise RuntimeControlDomainError("Kill switch is already engaged")
        raise RuntimeControlDomainError("Kill switch is not engaged")
    if (
        target_state is RuntimeControlState.ACTIVE
        and incident is not None
        and incident.status is IncidentStatus.CLOSED
    ):
        raise RuntimeControlDomainError("Cannot engage a kill switch on a closed incident")

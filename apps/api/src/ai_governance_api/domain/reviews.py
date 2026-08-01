"""Pure review-round transitions and segregation-of-duties rules."""

from dataclasses import dataclass

from governance_schemas import ApprovalArea, ApprovalStatus, EntityStatus, RiskTier


class ReviewDomainError(Exception):
    """Base class for expected review workflow failures."""


class ReviewConflict(ReviewDomainError):
    """Raised when state or optimistic version prevents a transition."""


class ReviewForbidden(ReviewDomainError):
    """Raised when an actor is not authorized for a review transition."""


@dataclass(frozen=True, slots=True)
class ReviewActor:
    """Authenticated actor used by review authorization policies."""

    user_id: str
    approval_areas: frozenset[ApprovalArea] = frozenset()
    is_admin: bool = False


@dataclass(frozen=True, slots=True)
class ReviewGateState:
    """Minimal immutable approval gate state used by domain policies."""

    id: str
    area: ApprovalArea
    required: bool
    status: ApprovalStatus
    review_round: int
    version: int
    decided_by: str | None = None


@dataclass(frozen=True, slots=True)
class InitiativeReviewState:
    """Minimal initiative state required to decide or resubmit a review round."""

    owner_id: str
    status: EntityStatus
    risk_tier: RiskTier
    version: int
    current_round: int
    gates: tuple[ReviewGateState, ...]


@dataclass(frozen=True, slots=True)
class GateDecisionTransition:
    """Result of one authorized gate decision."""

    resulting_status: EntityStatus
    superseded_gate_ids: tuple[str, ...]


def decide_gate(
    state: InitiativeReviewState,
    *,
    gate_id: str,
    decision: ApprovalStatus,
    expected_version: int,
    actor: ReviewActor,
) -> GateDecisionTransition:
    """Validate a gate decision and derive the resulting initiative state."""
    if state.status is not EntityStatus.UNDER_REVIEW:
        raise ReviewConflict("Initiative is not under review")
    gate = next((item for item in state.gates if item.id == gate_id), None)
    if gate is None:
        raise ReviewConflict("Approval does not belong to the current review round")
    if gate.review_round != state.current_round:
        raise ReviewConflict("Approval does not belong to the current review round")
    if not gate.required or gate.status is not ApprovalStatus.PENDING:
        raise ReviewConflict("Approval is not pending")
    if gate.version != expected_version:
        raise ReviewConflict("Version conflict")
    if state.owner_id == actor.user_id:
        raise ReviewForbidden("Segregation of duties prevents owner self-review")
    if gate.area not in actor.approval_areas and not actor.is_admin:
        raise ReviewForbidden(f"Principal cannot review for {gate.area.value}")
    if state.risk_tier in {RiskTier.HIGH, RiskTier.CRITICAL} and any(
        item.decided_by == actor.user_id
        for item in state.gates
        if item.review_round == state.current_round
    ):
        raise ReviewForbidden("High-risk gates require independent reviewers across areas")

    statuses = {
        item.id: decision if item.id == gate.id else item.status
        for item in state.gates
        if item.review_round == state.current_round and item.required
    }
    resulting_status = _resulting_status(tuple(statuses.values()))
    superseded = (
        tuple(
            item.id
            for item in state.gates
            if item.review_round == state.current_round
            and item.id != gate.id
            and item.status is ApprovalStatus.PENDING
        )
        if resulting_status in {EntityStatus.REJECTED, EntityStatus.CHANGES_REQUESTED}
        else ()
    )
    return GateDecisionTransition(
        resulting_status=resulting_status,
        superseded_gate_ids=superseded,
    )


def validate_resubmission(
    state: InitiativeReviewState,
    *,
    expected_version: int,
    actor: ReviewActor,
) -> None:
    """Allow only the owner to resubmit the current change-requested version."""
    if state.owner_id != actor.user_id:
        raise ReviewForbidden("Only the initiative owner can resubmit")
    if state.status is not EntityStatus.CHANGES_REQUESTED:
        raise ReviewConflict("Initiative does not have requested changes")
    if state.version != expected_version:
        raise ReviewConflict("Version conflict")


def _resulting_status(statuses: tuple[ApprovalStatus, ...]) -> EntityStatus:
    """Derive initiative state from all required gates in the current round."""
    if ApprovalStatus.CHANGES_REQUESTED in statuses:
        return EntityStatus.CHANGES_REQUESTED
    if ApprovalStatus.REJECTED in statuses:
        return EntityStatus.REJECTED
    if statuses and all(status is ApprovalStatus.APPROVED for status in statuses):
        return EntityStatus.APPROVED
    return EntityStatus.UNDER_REVIEW

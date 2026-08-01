"""Unit tests for framework-independent review workflow policies."""

import pytest
from ai_governance_api.domain.reviews import (
    InitiativeReviewState,
    ReviewActor,
    ReviewConflict,
    ReviewForbidden,
    ReviewGateState,
    decide_gate,
    validate_resubmission,
)
from governance_schemas import (
    ApprovalArea,
    ApprovalStatus,
    EntityStatus,
    RiskTier,
)


def gate(
    gate_id: str,
    area: ApprovalArea,
    *,
    status: ApprovalStatus = ApprovalStatus.PENDING,
    decided_by: str | None = None,
    review_round: int = 1,
) -> ReviewGateState:
    """Return a required review gate with stable defaults."""
    return ReviewGateState(
        id=gate_id,
        area=area,
        required=True,
        status=status,
        review_round=review_round,
        version=1,
        decided_by=decided_by,
    )


def state(**changes: object) -> InitiativeReviewState:
    """Return a review state suitable for transition tests."""
    values: dict[str, object] = {
        "owner_id": "owner-1",
        "status": EntityStatus.UNDER_REVIEW,
        "risk_tier": RiskTier.MEDIUM,
        "version": 2,
        "current_round": 1,
        "gates": (
            gate("business-1", ApprovalArea.BUSINESS),
            gate("security-1", ApprovalArea.SECURITY),
        ),
    }
    values.update(changes)
    return InitiativeReviewState(**values)  # type: ignore[arg-type]


def test_change_request_ends_current_round_and_supersedes_pending_gates() -> None:
    """A change request must preserve but close remaining current gates."""
    transition = decide_gate(
        state(),
        gate_id="security-1",
        decision=ApprovalStatus.CHANGES_REQUESTED,
        expected_version=1,
        actor=ReviewActor(
            user_id="security-reviewer",
            approval_areas=frozenset({ApprovalArea.SECURITY}),
        ),
    )

    assert transition.resulting_status is EntityStatus.CHANGES_REQUESTED
    assert transition.superseded_gate_ids == ("business-1",)


def test_approval_requires_current_pending_gate_and_authorized_reviewer() -> None:
    """Reject stale rounds, owner self-review, and unrelated reviewers."""
    with pytest.raises(ReviewConflict, match="current review round"):
        decide_gate(
            state(gates=(gate("old", ApprovalArea.BUSINESS, review_round=0),)),
            gate_id="old",
            decision=ApprovalStatus.APPROVED,
            expected_version=1,
            actor=ReviewActor(
                user_id="business-reviewer",
                approval_areas=frozenset({ApprovalArea.BUSINESS}),
            ),
        )

    with pytest.raises(ReviewForbidden, match="self-review"):
        decide_gate(
            state(),
            gate_id="business-1",
            decision=ApprovalStatus.APPROVED,
            expected_version=1,
            actor=ReviewActor(
                user_id="owner-1",
                approval_areas=frozenset({ApprovalArea.BUSINESS}),
            ),
        )

    with pytest.raises(ReviewForbidden, match="cannot review"):
        decide_gate(
            state(),
            gate_id="security-1",
            decision=ApprovalStatus.APPROVED,
            expected_version=1,
            actor=ReviewActor(
                user_id="business-reviewer",
                approval_areas=frozenset({ApprovalArea.BUSINESS}),
            ),
        )


def test_high_risk_review_requires_independent_people_across_areas() -> None:
    """One person cannot approve multiple high-risk functional gates."""
    high_risk = state(
        risk_tier=RiskTier.HIGH,
        gates=(
            gate(
                "business-1",
                ApprovalArea.BUSINESS,
                status=ApprovalStatus.APPROVED,
                decided_by="same-reviewer",
            ),
            gate("security-1", ApprovalArea.SECURITY),
        ),
    )

    with pytest.raises(ReviewForbidden, match="independent reviewers"):
        decide_gate(
            high_risk,
            gate_id="security-1",
            decision=ApprovalStatus.APPROVED,
            expected_version=1,
            actor=ReviewActor(
                user_id="same-reviewer",
                approval_areas=frozenset({ApprovalArea.SECURITY}),
            ),
        )


def test_resubmission_is_owner_controlled_and_versioned() -> None:
    """Only the owner can resubmit the exact change-requested projection."""
    requested = state(status=EntityStatus.CHANGES_REQUESTED, version=4)
    validate_resubmission(
        requested,
        expected_version=4,
        actor=ReviewActor(user_id="owner-1"),
    )

    with pytest.raises(ReviewForbidden, match="owner"):
        validate_resubmission(
            requested,
            expected_version=4,
            actor=ReviewActor(user_id="other-user"),
        )
    with pytest.raises(ReviewConflict, match="Version conflict"):
        validate_resubmission(
            requested,
            expected_version=3,
            actor=ReviewActor(user_id="owner-1"),
        )

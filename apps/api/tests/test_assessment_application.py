"""Unit tests for transport-independent structured assessment use cases."""

from datetime import UTC, datetime

import pytest
from ai_governance_api.application.assessments import (
    ListAssessments,
    SaveAssessment,
    SubmitAssessment,
)
from ai_governance_api.domain.assessments import (
    AIImpactAnswers,
    AssessmentActor,
    AssessmentKind,
    AssessmentRecord,
    InitiativeAssessmentContext,
    RIPDAnswers,
)
from ai_governance_api.errors import ApplicationError, ErrorKind
from governance_schemas import EntityStatus, RiskTier

FIXED_TIME = datetime(2026, 7, 31, 20, 0, tzinfo=UTC)


class FakeAssessmentStore:
    """In-memory test adapter implementing the use-case-owned store protocol."""

    def __init__(self, initiative: InitiativeAssessmentContext) -> None:
        """Initialize the adapter with one initiative context."""
        self.initiative = initiative
        self.records: dict[str, AssessmentRecord] = {}

    async def get_initiative(
        self,
        initiative_id: str,
    ) -> InitiativeAssessmentContext | None:
        """Return the configured initiative when identifiers match."""
        return self.initiative if initiative_id == self.initiative.id else None

    async def list_for_initiative(self, initiative_id: str) -> list[AssessmentRecord]:
        """Return matching records ordered by definition."""
        return sorted(
            (
                record
                for record in self.records.values()
                if record.initiative_id == initiative_id
            ),
            key=lambda record: record.kind.value,
        )

    async def get_by_id(self, assessment_id: str) -> AssessmentRecord | None:
        """Return a record by identifier."""
        return self.records.get(assessment_id)

    async def get_by_kind(
        self,
        initiative_id: str,
        kind: AssessmentKind,
    ) -> AssessmentRecord | None:
        """Return a record by initiative and definition."""
        return next(
            (
                record
                for record in self.records.values()
                if record.initiative_id == initiative_id and record.kind is kind
            ),
            None,
        )

    async def save(self, record: AssessmentRecord) -> AssessmentRecord:
        """Store and return the immutable record."""
        self.records[record.id] = record
        return record


class FakeAssessmentAudit:
    """Capture minimized application audit events for assertions."""

    def __init__(self) -> None:
        """Initialize an empty event collection."""
        self.events: list[dict[str, object]] = []

    async def append(
        self,
        *,
        actor_id: str,
        action: str,
        record: AssessmentRecord,
        changed_fields: tuple[str, ...],
    ) -> None:
        """Capture metadata without assessment answer content."""
        self.events.append(
            {
                "actor_id": actor_id,
                "action": action,
                "assessment_id": record.id,
                "changed_fields": changed_fields,
            }
        )


class FakeTransaction:
    """Count committed application transactions."""

    def __init__(self) -> None:
        """Initialize a transaction with no commits."""
        self.commits = 0

    async def commit(self) -> None:
        """Record a successful commit."""
        self.commits += 1


def initiative_context(**changes: object) -> InitiativeAssessmentContext:
    """Create an assessable initiative context for use-case tests."""
    values: dict[str, object] = {
        "id": "initiative-1",
        "business_owner_id": "owner-1",
        "status": EntityStatus.UNDER_REVIEW,
        "personal_data": True,
        "international_processing": True,
    }
    values.update(changes)
    return InitiativeAssessmentContext(**values)  # type: ignore[arg-type]


def impact_answers(risk: RiskTier = RiskTier.MEDIUM) -> AIImpactAnswers:
    """Return complete AI impact answers."""
    return AIImpactAnswers(
        affected_groups=("customers",),
        intended_benefits="Improve access to accurate support information.",
        potential_harms=("incorrect guidance",),
        human_oversight="A trained reviewer handles material or disputed answers.",
        contestability="Users can request human review through the support channel.",
        mitigation_measures=("grounding evaluation", "human escalation"),
        residual_risk=risk,
    )


async def test_save_update_list_and_submit_are_port_driven() -> None:
    """Exercise the complete use-case lifecycle using only fake ports."""
    store = FakeAssessmentStore(initiative_context())
    audit = FakeAssessmentAudit()
    transaction = FakeTransaction()
    save = SaveAssessment(
        store,
        audit,
        transaction,
        clock=lambda: FIXED_TIME,
        id_factory=lambda: "assessment-1",
    )

    created = await save.execute(
        initiative_id="initiative-1",
        kind=AssessmentKind.AI_IMPACT,
        answers=impact_answers(),
        actor=AssessmentActor("owner-1"),
        expected_version=None,
    )
    assert created.status is EntityStatus.DRAFT
    assert created.risk_score == 40
    assert audit.events[0]["action"] == "assessment.created"
    assert "answers" not in audit.events[0]

    updated = await save.execute(
        initiative_id="initiative-1",
        kind=AssessmentKind.AI_IMPACT,
        answers=impact_answers(RiskTier.HIGH),
        actor=AssessmentActor("owner-1"),
        expected_version=created.version,
    )
    assert updated.version == 2
    assert updated.risk_tier is RiskTier.HIGH
    assert len(await ListAssessments(store).execute("initiative-1")) == 1

    submitted = await SubmitAssessment(
        store,
        audit,
        transaction,
        clock=lambda: FIXED_TIME,
    ).execute(
        assessment_id=updated.id,
        expected_version=updated.version,
        actor=AssessmentActor("owner-1"),
    )
    assert submitted.status is EntityStatus.UNDER_REVIEW
    assert submitted.version == 3
    assert transaction.commits == 3

    with pytest.raises(ApplicationError) as conflict:
        await save.execute(
            initiative_id="initiative-1",
            kind=AssessmentKind.AI_IMPACT,
            answers=impact_answers(),
            actor=AssessmentActor("owner-1"),
            expected_version=submitted.version,
        )
    assert conflict.value.kind is ErrorKind.CONFLICT


async def test_applicability_and_owner_are_enforced_before_persistence() -> None:
    """Reject inapplicable RIPD and unauthorized assessment changes."""
    store = FakeAssessmentStore(initiative_context(personal_data=False))
    audit = FakeAssessmentAudit()
    transaction = FakeTransaction()
    save = SaveAssessment(store, audit, transaction, id_factory=lambda: "assessment-1")
    ripd = RIPDAnswers(
        controller_area="Privacy",
        processing_purpose="Support customers with contextual information.",
        personal_data_categories=("contact data",),
        data_subjects=("customers",),
        legal_basis="legitimate interest assessment",
        necessity_assessment="Only the minimum customer context is processed.",
        risk_scenarios=("unauthorized disclosure",),
        safeguards=("access control",),
        residual_risk=RiskTier.MEDIUM,
    )

    with pytest.raises(ApplicationError) as not_applicable:
        await save.execute(
            initiative_id="initiative-1",
            kind=AssessmentKind.RIPD,
            answers=ripd,
            actor=AssessmentActor("owner-1"),
            expected_version=None,
        )
    assert not_applicable.value.kind is ErrorKind.UNPROCESSABLE

    with pytest.raises(ApplicationError) as forbidden:
        await save.execute(
            initiative_id="initiative-1",
            kind=AssessmentKind.AI_IMPACT,
            answers=impact_answers(),
            actor=AssessmentActor("unrelated-user"),
            expected_version=None,
        )
    assert forbidden.value.kind is ErrorKind.FORBIDDEN
    assert not store.records

"""Assessment use cases and the ports they consume."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import NoReturn, Protocol
from uuid import uuid4

from governance_schemas import EntityStatus

from ai_governance_api.domain.assessments import (
    SCHEMA_VERSIONS,
    AssessmentActor,
    AssessmentAnswers,
    AssessmentDomainError,
    AssessmentKind,
    AssessmentNotApplicable,
    AssessmentNotEditable,
    AssessmentRecord,
    InitiativeAssessmentContext,
    risk_score,
    submit_draft,
    update_draft,
    validate_applicability,
    validate_definition,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

type Clock = Callable[[], datetime]
type IdFactory = Callable[[], str]


class AssessmentStore(Protocol):
    """Consumer-owned persistence operations required by assessment use cases."""

    async def get_initiative(
        self,
        initiative_id: str,
    ) -> InitiativeAssessmentContext | None:
        """Return the minimal initiative context or ``None`` when absent."""
        ...

    async def list_for_initiative(self, initiative_id: str) -> list[AssessmentRecord]:
        """Return assessments for an initiative in a stable order."""
        ...

    async def get_by_id(self, assessment_id: str) -> AssessmentRecord | None:
        """Return an assessment by identifier."""
        ...

    async def get_by_kind(
        self,
        initiative_id: str,
        kind: AssessmentKind,
    ) -> AssessmentRecord | None:
        """Return the current assessment for one initiative and definition."""
        ...

    async def save(self, record: AssessmentRecord) -> AssessmentRecord:
        """Persist a new or updated assessment and return its stored representation."""
        ...


class AssessmentAuditPort(Protocol):
    """Consumer-owned audit operation used by assessment commands."""

    async def append(
        self,
        *,
        actor_id: str,
        action: str,
        record: AssessmentRecord,
        changed_fields: tuple[str, ...],
    ) -> None:
        """Append a content-minimized audit event for an assessment change."""
        ...


class TransactionPort(Protocol):
    """Transaction boundary required by state-changing assessment use cases."""

    async def commit(self) -> None:
        """Atomically commit persistence and audit changes."""
        ...


class SaveAssessment:
    """Create or update one structured assessment draft."""

    def __init__(
        self,
        store: AssessmentStore,
        audit: AssessmentAuditPort,
        transaction: TransactionPort,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        """Initialize the use case with ports and deterministic test seams."""
        self._store = store
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def execute(
        self,
        *,
        initiative_id: str,
        kind: AssessmentKind,
        answers: AssessmentAnswers,
        actor: AssessmentActor,
        expected_version: int | None,
    ) -> AssessmentRecord:
        """Save a validated draft and emit an audit event without answer content."""
        initiative = await _require_initiative(self._store, initiative_id)
        _require_owner(initiative, actor)
        try:
            validate_definition(kind, answers)
            validate_applicability(kind, initiative)
        except AssessmentDomainError as exc:
            _raise_domain_error(exc)

        now = self._clock()
        current = await self._store.get_by_kind(initiative_id, kind)
        if current is None:
            if expected_version is not None:
                raise ApplicationError(ErrorKind.CONFLICT, "Assessment does not exist")
            record = AssessmentRecord(
                id=self._id_factory(),
                initiative_id=initiative_id,
                kind=kind,
                schema_version=SCHEMA_VERSIONS[kind],
                status=EntityStatus.DRAFT,
                answers=answers,
                risk_score=risk_score(answers),
                risk_tier=answers.residual_risk,
                assessed_by=actor.user_id,
                version=1,
                created_at=now,
                updated_at=now,
            )
            action = "assessment.created"
        else:
            _require_version(current.version, expected_version)
            try:
                record = update_draft(current, answers, actor.user_id, now)
            except AssessmentDomainError as exc:
                _raise_domain_error(exc)
            action = "assessment.updated"

        stored = await self._store.save(record)
        await self._audit.append(
            actor_id=actor.user_id,
            action=action,
            record=stored,
            changed_fields=("answers", "risk_score", "risk_tier"),
        )
        await self._transaction.commit()
        return stored


class ListAssessments:
    """List structured assessments for one initiative."""

    def __init__(self, store: AssessmentStore) -> None:
        """Initialize the query with its consumer-owned store."""
        self._store = store

    async def execute(self, initiative_id: str) -> list[AssessmentRecord]:
        """Return assessments after confirming the initiative exists."""
        await _require_initiative(self._store, initiative_id)
        return await self._store.list_for_initiative(initiative_id)


class SubmitAssessment:
    """Submit a complete draft assessment for independent review."""

    def __init__(
        self,
        store: AssessmentStore,
        audit: AssessmentAuditPort,
        transaction: TransactionPort,
        *,
        clock: Clock | None = None,
    ) -> None:
        """Initialize the command with persistence, audit, and clock ports."""
        self._store = store
        self._audit = audit
        self._transaction = transaction
        self._clock = clock or (lambda: datetime.now(UTC))

    async def execute(
        self,
        *,
        assessment_id: str,
        expected_version: int,
        actor: AssessmentActor,
    ) -> AssessmentRecord:
        """Move a draft to review using optimistic concurrency."""
        current = await self._store.get_by_id(assessment_id)
        if current is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Assessment not found")
        initiative = await _require_initiative(self._store, current.initiative_id)
        _require_owner(initiative, actor)
        _require_version(current.version, expected_version)
        try:
            submitted = submit_draft(current, self._clock())
        except AssessmentDomainError as exc:
            _raise_domain_error(exc)
        stored = await self._store.save(submitted)
        await self._audit.append(
            actor_id=actor.user_id,
            action="assessment.submitted",
            record=stored,
            changed_fields=("status",),
        )
        await self._transaction.commit()
        return stored


async def _require_initiative(
    store: AssessmentStore,
    initiative_id: str,
) -> InitiativeAssessmentContext:
    """Return initiative context or raise a stable not-found error."""
    initiative = await store.get_initiative(initiative_id)
    if initiative is None:
        raise ApplicationError(ErrorKind.NOT_FOUND, "Initiative not found")
    return initiative


def _require_owner(
    initiative: InitiativeAssessmentContext,
    actor: AssessmentActor,
) -> None:
    """Require the initiative owner or a governance administrator."""
    if initiative.business_owner_id != actor.user_id and not actor.is_admin:
        raise ApplicationError(
            ErrorKind.FORBIDDEN,
            "Only the initiative owner or an administrator can change assessments",
        )


def _require_version(current: int, expected: int | None) -> None:
    """Enforce optimistic concurrency for assessment commands."""
    if expected is None or current != expected:
        raise ApplicationError(ErrorKind.CONFLICT, "Version conflict")


def _raise_domain_error(error: AssessmentDomainError) -> NoReturn:
    """Translate typed domain errors into stable application categories."""
    if isinstance(error, AssessmentNotEditable):
        raise ApplicationError(ErrorKind.CONFLICT, str(error)) from error
    if isinstance(error, AssessmentNotApplicable):
        raise ApplicationError(ErrorKind.UNPROCESSABLE, str(error)) from error
    raise ApplicationError(ErrorKind.UNPROCESSABLE, str(error)) from error

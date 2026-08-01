"""SQLAlchemy adapters for structured assessment application ports."""

from dataclasses import asdict
from typing import Any

from governance_schemas import RiskTier
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.audit import append_audit_event
from ai_governance_api.domain.assessments import (
    AIImpactAnswers,
    AssessmentAnswers,
    AssessmentKind,
    AssessmentRecord,
    InitiativeAssessmentContext,
    InternationalProcessingAnswers,
    RIPDAnswers,
    Subprocessor,
)
from ai_governance_api.models import Assessment, Initiative


class SqlAlchemyAssessmentStore:
    """Persist assessment domain records through a request-scoped SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the store with its backing-service session."""
        self._session = session

    async def get_initiative(
        self,
        initiative_id: str,
    ) -> InitiativeAssessmentContext | None:
        """Map a persistence initiative into the domain policy context."""
        initiative = await self._session.get(Initiative, initiative_id)
        if initiative is None:
            return None
        return InitiativeAssessmentContext(
            id=initiative.id,
            business_owner_id=initiative.business_owner_id,
            status=initiative.status,
            personal_data=initiative.personal_data,
            international_processing=initiative.international_processing,
        )

    async def list_for_initiative(self, initiative_id: str) -> list[AssessmentRecord]:
        """Return assessments ordered by their stable definition identifier."""
        entities = await self._session.scalars(
            select(Assessment)
            .where(Assessment.initiative_id == initiative_id)
            .order_by(Assessment.assessment_type)
        )
        return [_to_domain(entity) for entity in entities]

    async def get_by_id(self, assessment_id: str) -> AssessmentRecord | None:
        """Return one mapped assessment or ``None``."""
        entity = await self._session.get(Assessment, assessment_id)
        return _to_domain(entity) if entity is not None else None

    async def get_by_kind(
        self,
        initiative_id: str,
        kind: AssessmentKind,
    ) -> AssessmentRecord | None:
        """Return the current assessment for an initiative and definition."""
        entity = await self._session.scalar(
            select(Assessment).where(
                Assessment.initiative_id == initiative_id,
                Assessment.assessment_type == kind.value,
            )
        )
        return _to_domain(entity) if entity is not None else None

    async def save(self, record: AssessmentRecord) -> AssessmentRecord:
        """Insert or update a domain record without committing the transaction."""
        entity = await self._session.get(Assessment, record.id)
        values = {
            "initiative_id": record.initiative_id,
            "assessment_type": record.kind.value,
            "schema_version": record.schema_version,
            "status": record.status,
            "answers": _serialize_answers(record.answers),
            "risk_score": record.risk_score,
            "risk_tier": record.risk_tier,
            "assessed_by": record.assessed_by,
            "version": record.version,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
        if entity is None:
            entity = Assessment(id=record.id, **values)
            self._session.add(entity)
        else:
            for field, value in values.items():
                setattr(entity, field, value)
        await self._session.flush()
        return _to_domain(entity)


class SqlAlchemyAssessmentAudit:
    """Append assessment events to the shared tamper-evident audit chain."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the audit adapter with the transaction session."""
        self._session = session

    async def append(
        self,
        *,
        actor_id: str,
        action: str,
        record: AssessmentRecord,
        changed_fields: tuple[str, ...],
    ) -> None:
        """Record metadata and decisions without copying assessment answer content."""
        await append_audit_event(
            self._session,
            actor_id=actor_id,
            action=action,
            entity_type="assessment",
            entity_id=record.id,
            entity_version=record.version,
            payload={
                "initiative_id": record.initiative_id,
                "assessment_type": record.kind.value,
                "schema_version": record.schema_version,
                "risk_tier": record.risk_tier.value,
                "changed_fields": list(changed_fields),
            },
        )


class SqlAlchemyTransaction:
    """Manage an application transaction through a request-scoped session."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the transaction adapter with a request-scoped session."""
        self._session = session

    async def commit(self) -> None:
        """Commit all pending changes in the request transaction."""
        await self._session.commit()

    async def rollback(self) -> None:
        """Discard pending changes after a failed multi-resource operation."""
        await self._session.rollback()


def _serialize_answers(answers: AssessmentAnswers) -> dict[str, Any]:
    """Convert pure domain answers into a JSON-compatible persistence mapping."""
    return asdict(answers)


def _to_domain(entity: Assessment) -> AssessmentRecord:
    """Map an ORM assessment into its pure domain representation."""
    kind = AssessmentKind(entity.assessment_type)
    return AssessmentRecord(
        id=entity.id,
        initiative_id=entity.initiative_id,
        kind=kind,
        schema_version=entity.schema_version,
        status=entity.status,
        answers=_deserialize_answers(kind, entity.answers),
        risk_score=entity.risk_score or 0,
        risk_tier=entity.risk_tier or RiskTier.LOW,
        assessed_by=entity.assessed_by,
        version=entity.version,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _deserialize_answers(
    kind: AssessmentKind,
    values: dict[str, Any],
) -> AssessmentAnswers:
    """Rehydrate the definition-specific pure answer value from JSON."""
    residual_risk = RiskTier(values["residual_risk"])
    if kind is AssessmentKind.AI_IMPACT:
        return AIImpactAnswers(
            affected_groups=_strings(values, "affected_groups"),
            intended_benefits=str(values["intended_benefits"]),
            potential_harms=_strings(values, "potential_harms"),
            human_oversight=str(values["human_oversight"]),
            contestability=str(values["contestability"]),
            mitigation_measures=_strings(values, "mitigation_measures"),
            residual_risk=residual_risk,
        )
    if kind is AssessmentKind.RIPD:
        return RIPDAnswers(
            controller_area=str(values["controller_area"]),
            processing_purpose=str(values["processing_purpose"]),
            personal_data_categories=_strings(values, "personal_data_categories"),
            data_subjects=_strings(values, "data_subjects"),
            legal_basis=str(values["legal_basis"]),
            necessity_assessment=str(values["necessity_assessment"]),
            risk_scenarios=_strings(values, "risk_scenarios"),
            safeguards=_strings(values, "safeguards"),
            residual_risk=residual_risk,
        )
    subprocessors = tuple(
        Subprocessor(
            name=str(item["name"]),
            countries=tuple(str(country) for country in item["countries"]),
            purpose=str(item["purpose"]),
        )
        for item in values["subprocessors"]
    )
    return InternationalProcessingAnswers(
        data_categories=_strings(values, "data_categories"),
        source_country=str(values["source_country"]),
        inference_countries=_strings(values, "inference_countries"),
        storage_regions=_strings(values, "storage_regions"),
        log_regions=_strings(values, "log_regions"),
        subprocessors=subprocessors,
        transfer_mechanism=str(values["transfer_mechanism"]),
        legal_basis=str(values["legal_basis"]),
        safeguards=_strings(values, "safeguards"),
        residual_risk=residual_risk,
    )


def _strings(values: dict[str, Any], key: str) -> tuple[str, ...]:
    """Return a stored JSON list as an immutable string tuple."""
    return tuple(str(item) for item in values[key])

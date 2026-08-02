"""SQLAlchemy adapters for governed model-routing decisions."""

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal

from governance_schemas import DataClassification, RiskTier
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from ai_governance_api.audit import append_audit_event
from ai_governance_api.domain.model_routing import (
    GovernedRoutingModel,
    GovernedRoutingScope,
    ModelRoutingCommand,
    ModelRoutingDecisionRecord,
    RejectedRoutingCandidate,
    RouterDecisionOutcome,
    RoutingDecisionSource,
    RoutingEnforcementOutcome,
    RoutingWorkload,
)
from ai_governance_api.models import (
    Agent,
    AISystem,
    ModelRoutingDecisionEntry,
)


class SqlAlchemyModelRoutingScopeReader:
    """Load fresh registry scope through short-lived database transactions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the reader with the application session factory."""
        self._session_factory = session_factory

    async def get(self, agent_id: str) -> GovernedRoutingScope | None:
        """Return one agent and its model dependencies without retaining a session."""
        async with self._session_factory() as session:
            agent = await session.scalar(
                select(Agent)
                .where(Agent.id == agent_id)
                .options(
                    joinedload(Agent.ai_system).joinedload(AISystem.initiative),
                    joinedload(Agent.ai_system).selectinload(AISystem.models),
                )
                .execution_options(populate_existing=True)
            )
            if agent is None:
                return None
            ai_system = agent.ai_system
            initiative = ai_system.initiative
            return GovernedRoutingScope(
                ai_system_id=ai_system.id,
                ai_system_version=ai_system.version,
                ai_system_owner_id=ai_system.owner_id,
                ai_system_status=ai_system.status,
                risk_tier=ai_system.risk_tier,
                data_classification=initiative.data_classification,
                initiative_id=initiative.id,
                agent_id=agent.id,
                agent_version=agent.version,
                agent_name=agent.name,
                agent_owner_id=agent.owner_id,
                agent_status=agent.status,
                agent_approved_scope_digest=agent.approved_scope_digest,
                agent_next_review_at=_optional_utc(agent.next_review_at),
                agent_allowed_model_ids=tuple(agent.allowed_models),
                agent_max_cost=(
                    Decimal(str(agent.max_cost)) if agent.max_cost is not None else None
                ),
                models=tuple(
                    GovernedRoutingModel(
                        id=model.id,
                        version=model.version,
                        status=model.status,
                        routing_group=model.routing_group,
                        allowed_data_classes=tuple(model.allowed_data_classes),
                        approved_scope_digest=model.approved_scope_digest,
                        next_review_at=_optional_utc(model.next_review_at),
                    )
                    for model in ai_system.models
                ),
            )


class SqlAlchemyModelRoutingDecisionStore:
    """Persist routing attempts and their immutable completed projections."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the store with a request-scoped database session."""
        self._session = session

    async def save(
        self,
        record: ModelRoutingDecisionRecord,
    ) -> ModelRoutingDecisionRecord:
        """Insert a pending attempt or finalize its existing row."""
        entity = await self._session.get(ModelRoutingDecisionEntry, record.id)
        values = _record_values(record)
        if entity is None:
            entity = ModelRoutingDecisionEntry(id=record.id, **values)
            self._session.add(entity)
        else:
            if entity.outcome != RoutingEnforcementOutcome.PENDING.value:
                raise ValueError("Completed routing evidence is immutable")
            if record.version != entity.version + 1:
                raise ValueError("Routing evidence version conflict")
            for field, value in values.items():
                setattr(entity, field, value)
        await self._session.flush()
        return _to_domain(entity)

    async def list_for_agent(self, agent_id: str) -> list[ModelRoutingDecisionRecord]:
        """Return newest routing attempts first for one governed agent."""
        entities = await self._session.scalars(
            select(ModelRoutingDecisionEntry)
            .where(ModelRoutingDecisionEntry.agent_id == agent_id)
            .order_by(
                ModelRoutingDecisionEntry.requested_at.desc(),
                ModelRoutingDecisionEntry.id.desc(),
            )
        )
        return [_to_domain(entity) for entity in entities]


class SqlAlchemyModelRoutingAudit:
    """Append minimized model-routing events to the shared audit chain."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the adapter with the routing evidence transaction."""
        self._session = session

    async def append(
        self,
        *,
        actor_id: str,
        action: str,
        record: ModelRoutingDecisionRecord,
    ) -> None:
        """Record constraints and provenance without prompts or response content."""
        payload: dict[str, object] = {
            "initiative_id": record.initiative_id,
            "ai_system_id": record.ai_system_id,
            "agent_id": record.agent_id,
            "workflow_id": record.command.workflow_id,
            "task_id": record.command.task_id,
            "workload": record.command.workload.value,
            "risk_level": record.risk_level.value,
            "data_classification": record.data_classification.value,
            "scope_digest": record.scope_digest,
            "outcome": record.outcome.value,
        }
        if record.decision_source is not None:
            payload["decision_source"] = record.decision_source.value
        if record.router_decision_id is not None:
            payload["router_decision_id"] = record.router_decision_id
        if record.selected_model_group is not None:
            payload["selected_model_group"] = record.selected_model_group
        if record.reason_code is not None:
            payload["reason_code"] = record.reason_code
        if record.policy_id is not None:
            payload.update(
                {
                    "policy_id": record.policy_id,
                    "policy_version": record.policy_version,
                    "policy_digest": record.policy_digest,
                    "service_version": record.service_version,
                    "environment": record.environment,
                }
            )
        await append_audit_event(
            self._session,
            actor_id=actor_id,
            action=action,
            entity_type="model_routing_decision",
            entity_id=record.id,
            entity_version=record.version,
            payload=payload,
        )


def _record_values(record: ModelRoutingDecisionRecord) -> dict[str, object]:
    """Map a pure routing record into persistence column values."""
    return {
        "ai_system_id": record.ai_system_id,
        "initiative_id": record.initiative_id,
        "agent_id": record.agent_id,
        "requested_by": record.requested_by,
        "requested_at": record.requested_at,
        "scope_digest": record.scope_digest,
        "workflow_id": record.command.workflow_id,
        "task_id": record.command.task_id,
        "workload": record.command.workload.value,
        "risk_level": record.risk_level.value,
        "data_classification": record.data_classification.value,
        "context_tokens_estimated": record.command.context_tokens_estimated,
        "max_output_tokens_estimated": record.command.max_output_tokens_estimated,
        "structured_output_required": record.command.structured_output_required,
        "max_latency_ms": record.command.max_latency_ms,
        "max_cost_usd": record.command.max_cost_usd,
        "outcome": record.outcome.value,
        "decision_source": (
            record.decision_source.value if record.decision_source is not None else None
        ),
        "router_decision_id": record.router_decision_id,
        "router_outcome": (
            record.router_outcome.value if record.router_outcome is not None else None
        ),
        "decided_at": record.decided_at,
        "selected_model_group": record.selected_model_group,
        "rejected_model_group": record.rejected_model_group,
        "reason": record.reason,
        "reason_code": record.reason_code,
        "observed_value": record.observed_value,
        "required_value": record.required_value,
        "rejected_candidates": [asdict(candidate) for candidate in record.rejected_candidates],
        "policy_id": record.policy_id,
        "policy_version": record.policy_version,
        "policy_digest": record.policy_digest,
        "service_version": record.service_version,
        "environment": record.environment,
        "version": record.version,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _to_domain(entity: ModelRoutingDecisionEntry) -> ModelRoutingDecisionRecord:
    """Map one persistence row into the pure routing evidence record."""
    return ModelRoutingDecisionRecord(
        id=entity.id,
        ai_system_id=entity.ai_system_id,
        initiative_id=entity.initiative_id,
        agent_id=entity.agent_id,
        requested_by=entity.requested_by,
        requested_at=_as_utc(entity.requested_at),
        scope_digest=entity.scope_digest,
        command=ModelRoutingCommand(
            workflow_id=entity.workflow_id,
            task_id=entity.task_id,
            workload=RoutingWorkload(entity.workload),
            context_tokens_estimated=entity.context_tokens_estimated,
            max_output_tokens_estimated=entity.max_output_tokens_estimated,
            structured_output_required=entity.structured_output_required,
            max_latency_ms=entity.max_latency_ms,
            max_cost_usd=Decimal(entity.max_cost_usd),
        ),
        risk_level=RiskTier(entity.risk_level),
        data_classification=DataClassification(entity.data_classification),
        outcome=RoutingEnforcementOutcome(entity.outcome),
        decision_source=(
            RoutingDecisionSource(entity.decision_source)
            if entity.decision_source is not None
            else None
        ),
        router_decision_id=entity.router_decision_id,
        router_outcome=(
            RouterDecisionOutcome(entity.router_outcome)
            if entity.router_outcome is not None
            else None
        ),
        decided_at=_optional_utc(entity.decided_at),
        selected_model_group=entity.selected_model_group,
        rejected_model_group=entity.rejected_model_group,
        reason=entity.reason,
        reason_code=entity.reason_code,
        observed_value=entity.observed_value,
        required_value=entity.required_value,
        rejected_candidates=tuple(
            RejectedRoutingCandidate(**candidate)
            for candidate in entity.rejected_candidates
        ),
        policy_id=entity.policy_id,
        policy_version=entity.policy_version,
        policy_digest=entity.policy_digest,
        service_version=entity.service_version,
        environment=entity.environment,
        version=entity.version,
        created_at=_as_utc(entity.created_at),
        updated_at=_as_utc(entity.updated_at),
    )


def _optional_utc(value: datetime | None) -> datetime | None:
    """Normalize an optional database timestamp to UTC."""
    return _as_utc(value) if value is not None else None


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive and PostgreSQL-aware timestamps to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

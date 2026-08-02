"""Application service for the operational AI inventory."""

import hashlib
from datetime import UTC, datetime
from typing import Any, NoReturn, cast

from governance_schemas import EntityStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_governance_api.audit import append_audit_event
from ai_governance_api.domain.asset_registry import (
    AgentReviewCandidate,
    AssetReviewContext,
    AssetReviewDecision,
    AssetReviewError,
    AssetReviewForbidden,
    ModelReviewCandidate,
    review_agent_scope,
    review_is_current,
    review_model_scope,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.errors import ApplicationError, ErrorKind
from ai_governance_api.models import Agent, AISystem, AuditEvent, Initiative, ModelAsset
from ai_governance_api.schemas import (
    AgentCreate,
    AgentUpdate,
    AISystemCreate,
    AISystemUpdate,
    AssetReviewRequest,
    ModelAssetCreate,
    ModelAssetUpdate,
    RetirementRequest,
)

MUTABLE_SYSTEM_STATUSES = {EntityStatus.APPROVED, EntityStatus.ACTIVE}
AUDIT_ENTITY_TYPES = {
    "systems": "ai_system",
    "models": "model_asset",
    "agents": "agent",
}


class InventoryService:
    """Coordinate inventory commands, authorization, versioning, and audit events."""

    def __init__(self, session: AsyncSession) -> None:
        """Create a service using the request-scoped database session."""
        self._session = session

    async def create_system(
        self,
        initiative_id: str,
        request: AISystemCreate,
        principal: Principal,
    ) -> AISystem:
        """Create an AI system under an approved initiative."""
        initiative = await self._load_initiative(initiative_id)
        if initiative.status is not EntityStatus.APPROVED:
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "Only an approved initiative can create an AI system",
            )
        if initiative.business_owner_id != principal.user_id and not principal.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only the initiative owner or an administrator can create the AI system",
            )

        values = request.model_dump(exclude={"owner_id"})
        ai_system = AISystem(
            **values,
            initiative_id=initiative.id,
            owner_id=request.owner_id or principal.user_id,
            risk_tier=initiative.risk_tier,
            status=EntityStatus.ACTIVE if request.production else EntityStatus.APPROVED,
        )
        self._session.add(ai_system)
        await self._session.flush()
        await self._record_event(
            principal=principal,
            action="ai_system.created",
            entity_type="ai_system",
            entity_id=ai_system.id,
            entity_version=ai_system.version,
            initiative_id=initiative.id,
            ai_system_id=ai_system.id,
            extra={"owner_id": ai_system.owner_id, "production": ai_system.production},
        )
        await self._session.commit()
        return await self.get_system(ai_system.id)

    async def list_systems(self) -> list[AISystem]:
        """Return AI systems ordered from newest to oldest."""
        result = await self._session.scalars(select(AISystem).order_by(AISystem.created_at.desc()))
        return list(result)

    async def get_system(self, system_id: str) -> AISystem:
        """Load an AI system aggregate with models and agents."""
        ai_system = await self._session.scalar(
            select(AISystem)
            .where(AISystem.id == system_id)
            .options(selectinload(AISystem.models), selectinload(AISystem.agents))
        )
        if ai_system is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "AI system not found")
        return ai_system

    async def _get_system_for_update(self, system_id: str) -> AISystem:
        """Lock one system as the serialization boundary for inventory commands."""
        ai_system = await self._session.scalar(
            select(AISystem)
            .where(AISystem.id == system_id)
            .with_for_update(of=AISystem)
            .options(selectinload(AISystem.models), selectinload(AISystem.agents))
        )
        if ai_system is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "AI system not found")
        return ai_system

    async def _get_model_for_update(
        self,
        model_id: str,
    ) -> tuple[AISystem, ModelAsset]:
        """Lock the owning system before evaluating a model mutation."""
        ai_system = await self._session.scalar(
            select(AISystem)
            .join(ModelAsset, ModelAsset.ai_system_id == AISystem.id)
            .where(ModelAsset.id == model_id)
            .with_for_update(of=AISystem)
            .options(selectinload(AISystem.models), selectinload(AISystem.agents))
        )
        if ai_system is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Model not found")
        model = next(item for item in ai_system.models if item.id == model_id)
        return ai_system, model

    async def _get_agent_for_update(
        self,
        agent_id: str,
    ) -> tuple[AISystem, Agent]:
        """Lock the owning system before evaluating an agent mutation."""
        ai_system = await self._session.scalar(
            select(AISystem)
            .join(Agent, Agent.ai_system_id == AISystem.id)
            .where(Agent.id == agent_id)
            .with_for_update(of=AISystem)
            .options(selectinload(AISystem.models), selectinload(AISystem.agents))
        )
        if ai_system is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Agent not found")
        agent = next(item for item in ai_system.agents if item.id == agent_id)
        return ai_system, agent

    async def update_system(
        self,
        system_id: str,
        request: AISystemUpdate,
        principal: Principal,
    ) -> AISystem:
        """Update a mutable AI system using optimistic concurrency."""
        ai_system = await self._get_system_for_update(system_id)
        self._require_owner(ai_system, principal)
        self._require_mutable(ai_system)
        self._require_version(ai_system.version, request.expected_version)

        changes = request.model_dump(mode="json", exclude_unset=True, exclude={"expected_version"})
        owner_changed = (
            "owner_id" in changes and changes["owner_id"] != ai_system.owner_id
        )
        self._apply_changes(ai_system, changes)
        invalidated_reviews = (
            await self._invalidate_system_asset_reviews(
                ai_system,
                principal,
                reason="system_owner_changed",
            )
            if owner_changed
            else 0
        )
        if "production" in changes:
            ai_system.status = (
                EntityStatus.ACTIVE if ai_system.production else EntityStatus.APPROVED
            )
        ai_system.version += 1
        await self._session.flush()
        await self._record_event(
            principal=principal,
            action="ai_system.updated",
            entity_type="ai_system",
            entity_id=ai_system.id,
            entity_version=ai_system.version,
            initiative_id=ai_system.initiative_id,
            ai_system_id=ai_system.id,
            extra={
                "changed_fields": sorted(changes),
                "asset_reviews_invalidated": invalidated_reviews,
            },
        )
        await self._session.commit()
        return await self.get_system(ai_system.id)

    async def retire_system(
        self,
        system_id: str,
        request: RetirementRequest,
        principal: Principal,
    ) -> AISystem:
        """Retire a system and cascade retirement to its active inventory."""
        ai_system = await self._get_system_for_update(system_id)
        self._require_owner(ai_system, principal)
        self._require_mutable(ai_system)
        self._require_version(ai_system.version, request.expected_version)

        retired_models = self._retire_entities(ai_system.models)
        retired_agents = self._retire_entities(ai_system.agents)
        ai_system.status = EntityStatus.RETIRED
        ai_system.production = False
        ai_system.version += 1
        await self._session.flush()

        reason_sha256 = self._reason_digest(request.reason)
        await self._record_cascade_events(
            ai_system,
            principal,
            retired_models,
            retired_agents,
            reason_sha256,
        )
        await self._record_event(
            principal=principal,
            action="ai_system.retired",
            entity_type="ai_system",
            entity_id=ai_system.id,
            entity_version=ai_system.version,
            initiative_id=ai_system.initiative_id,
            ai_system_id=ai_system.id,
            extra={
                "reason_sha256": reason_sha256,
                "retired_models": retired_models,
                "retired_agents": retired_agents,
            },
        )
        await self._session.commit()
        return await self.get_system(ai_system.id)

    async def create_model(
        self,
        system_id: str,
        request: ModelAssetCreate,
        principal: Principal,
    ) -> ModelAsset:
        """Register a model in a mutable AI system."""
        ai_system = await self._get_system_for_update(system_id)
        self._require_owner(ai_system, principal)
        self._require_mutable(ai_system)
        model = ModelAsset(
            **request.model_dump(),
            ai_system_id=ai_system.id,
            status=EntityStatus.DRAFT,
        )
        self._session.add(model)
        await self._session.flush()
        await self._record_event(
            principal=principal,
            action="model.created",
            entity_type="model_asset",
            entity_id=model.id,
            entity_version=model.version,
            initiative_id=ai_system.initiative_id,
            ai_system_id=ai_system.id,
            extra={"provider": model.provider, "deployment_region": model.deployment_region},
        )
        await self._session.commit()
        return model

    async def update_model(
        self,
        model_id: str,
        request: ModelAssetUpdate,
        principal: Principal,
    ) -> ModelAsset:
        """Update a registered model using optimistic concurrency."""
        ai_system, model = await self._get_model_for_update(model_id)
        self._require_owner(ai_system, principal)
        self._require_mutable(ai_system)
        self._require_not_retired(model.status, "Model")
        self._require_version(model.version, request.expected_version)
        changes = request.model_dump(exclude_unset=True, exclude={"expected_version"})
        review_invalidated = bool(changes) and self._clear_asset_review(model)
        self._apply_changes(model, changes)
        model.version += 1
        invalidated_agents = (
            await self._invalidate_agents_for_model(
                ai_system,
                model.id,
                principal,
                reason="model_scope_changed",
            )
            if review_invalidated
            else []
        )
        await self._session.flush()
        await self._record_event(
            principal=principal,
            action="model.updated",
            entity_type="model_asset",
            entity_id=model.id,
            entity_version=model.version,
            initiative_id=ai_system.initiative_id,
            ai_system_id=ai_system.id,
            extra={
                "changed_fields": sorted(changes),
                "review_invalidated": review_invalidated,
                "dependent_agent_reviews_invalidated": len(invalidated_agents),
            },
        )
        await self._session.commit()
        return model

    async def review_model(
        self,
        model_id: str,
        request: AssetReviewRequest,
        principal: Principal,
    ) -> ModelAsset:
        """Approve a model scope through an independent architecture review."""
        ai_system, model = await self._get_model_for_update(model_id)
        self._require_mutable(ai_system)
        self._require_not_retired(model.status, "Model")
        self._require_version(model.version, request.expected_version)
        reviewed_at = datetime.now(UTC)
        try:
            decision = review_model_scope(
                self._model_review_candidate(model),
                self._review_context(
                    ai_system,
                    principal,
                    reviewed_at=reviewed_at,
                    request=request,
                ),
            )
        except AssetReviewError as exc:
            self._raise_asset_review_error(exc)
        self._apply_review_decision(model, decision)
        model.version += 1
        await self._session.flush()
        await self._record_review_event(
            model,
            ai_system,
            principal,
            decision,
        )
        await self._session.commit()
        return model

    async def retire_model(
        self,
        model_id: str,
        request: RetirementRequest,
        principal: Principal,
    ) -> ModelAsset:
        """Retire a registered model without deleting its history."""
        ai_system, model = await self._get_model_for_update(model_id)
        self._require_owner(ai_system, principal)
        self._require_mutable(ai_system)
        self._require_not_retired(model.status, "Model")
        self._require_version(model.version, request.expected_version)
        model.status = EntityStatus.RETIRED
        model.version += 1
        invalidated_agents = await self._invalidate_agents_for_model(
            ai_system,
            model.id,
            principal,
            reason="model_retired",
        )
        await self._session.flush()
        await self._record_event(
            principal=principal,
            action="model.retired",
            entity_type="model_asset",
            entity_id=model.id,
            entity_version=model.version,
            initiative_id=ai_system.initiative_id,
            ai_system_id=ai_system.id,
            extra={
                "reason_sha256": self._reason_digest(request.reason),
                "dependent_agent_reviews_invalidated": len(invalidated_agents),
            },
        )
        await self._session.commit()
        return model

    async def create_agent(
        self,
        system_id: str,
        request: AgentCreate,
        principal: Principal,
    ) -> Agent:
        """Register an agent whose models belong to the same active system."""
        ai_system = await self._get_system_for_update(system_id)
        self._require_owner(ai_system, principal)
        self._require_mutable(ai_system)
        self._validate_allowed_models(ai_system, request.allowed_models)
        values = request.model_dump(exclude={"owner_id"})
        agent = Agent(
            **values,
            ai_system_id=ai_system.id,
            owner_id=request.owner_id or principal.user_id,
            status=EntityStatus.DRAFT,
        )
        self._session.add(agent)
        await self._session.flush()
        await self._record_event(
            principal=principal,
            action="agent.created",
            entity_type="agent",
            entity_id=agent.id,
            entity_version=agent.version,
            initiative_id=ai_system.initiative_id,
            ai_system_id=ai_system.id,
            extra={"owner_id": agent.owner_id, "autonomy_level": agent.autonomy_level.value},
        )
        await self._session.commit()
        return agent

    async def update_agent(
        self,
        agent_id: str,
        request: AgentUpdate,
        principal: Principal,
    ) -> Agent:
        """Update an agent while preserving system model boundaries."""
        ai_system, agent = await self._get_agent_for_update(agent_id)
        self._require_owner(ai_system, principal)
        self._require_mutable(ai_system)
        self._require_not_retired(agent.status, "Agent")
        self._require_version(agent.version, request.expected_version)
        changes = request.model_dump(exclude_unset=True, exclude={"expected_version"})
        if "allowed_models" in changes:
            self._validate_allowed_models(
                ai_system,
                cast(list[str], changes["allowed_models"]),
            )
        review_invalidated = bool(changes) and self._clear_asset_review(agent)
        self._apply_changes(agent, changes)
        agent.version += 1
        await self._session.flush()
        await self._record_event(
            principal=principal,
            action="agent.updated",
            entity_type="agent",
            entity_id=agent.id,
            entity_version=agent.version,
            initiative_id=ai_system.initiative_id,
            ai_system_id=ai_system.id,
            extra={
                "changed_fields": sorted(changes),
                "review_invalidated": review_invalidated,
            },
        )
        await self._session.commit()
        return agent

    async def review_agent(
        self,
        agent_id: str,
        request: AssetReviewRequest,
        principal: Principal,
    ) -> Agent:
        """Approve an agent scope through an independent security review."""
        ai_system, agent = await self._get_agent_for_update(agent_id)
        self._require_mutable(ai_system)
        self._require_not_retired(agent.status, "Agent")
        self._require_version(agent.version, request.expected_version)
        reviewed_at = datetime.now(UTC)
        self._require_current_approved_models(
            ai_system,
            agent.allowed_models,
            now=reviewed_at,
            agent_next_review_at=request.next_review_at,
        )
        try:
            decision = review_agent_scope(
                self._agent_review_candidate(agent),
                self._review_context(
                    ai_system,
                    principal,
                    reviewed_at=reviewed_at,
                    request=request,
                    additional_owner_ids=frozenset({agent.owner_id}),
                ),
            )
        except AssetReviewError as exc:
            self._raise_asset_review_error(exc)
        self._apply_review_decision(agent, decision)
        agent.version += 1
        await self._session.flush()
        await self._record_review_event(
            agent,
            ai_system,
            principal,
            decision,
        )
        await self._session.commit()
        return agent

    async def retire_agent(
        self,
        agent_id: str,
        request: RetirementRequest,
        principal: Principal,
    ) -> Agent:
        """Retire an agent without deleting its history."""
        ai_system, agent = await self._get_agent_for_update(agent_id)
        self._require_owner(ai_system, principal)
        self._require_mutable(ai_system)
        self._require_not_retired(agent.status, "Agent")
        self._require_version(agent.version, request.expected_version)
        agent.status = EntityStatus.RETIRED
        agent.version += 1
        await self._session.flush()
        await self._record_event(
            principal=principal,
            action="agent.retired",
            entity_type="agent",
            entity_id=agent.id,
            entity_version=agent.version,
            initiative_id=ai_system.initiative_id,
            ai_system_id=ai_system.id,
            extra={"reason_sha256": self._reason_digest(request.reason)},
        )
        await self._session.commit()
        return agent

    async def list_audit_events(self, entity_type: str, entity_id: str) -> list[AuditEvent]:
        """Return the ordered audit trail for a supported inventory entity."""
        normalized_type = AUDIT_ENTITY_TYPES.get(entity_type)
        if normalized_type is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Entity type not found")
        await self._ensure_entity_exists(normalized_type, entity_id)
        events = await self._session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == normalized_type,
                AuditEvent.entity_id == entity_id,
            )
            .order_by(AuditEvent.occurred_at)
        )
        return list(events)

    async def _load_initiative(self, initiative_id: str) -> Initiative:
        initiative = await self._session.get(Initiative, initiative_id)
        if initiative is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Initiative not found")
        return initiative

    async def _load_model(self, model_id: str) -> ModelAsset:
        model = await self._session.get(ModelAsset, model_id)
        if model is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Model not found")
        return model

    async def _load_agent(self, agent_id: str) -> Agent:
        agent = await self._session.get(Agent, agent_id)
        if agent is None:
            raise ApplicationError(ErrorKind.NOT_FOUND, "Agent not found")
        return agent

    async def _ensure_entity_exists(self, entity_type: str, entity_id: str) -> None:
        if entity_type == "ai_system":
            await self.get_system(entity_id)
        elif entity_type == "model_asset":
            await self._load_model(entity_id)
        else:
            await self._load_agent(entity_id)

    @staticmethod
    def _require_owner(ai_system: AISystem, principal: Principal) -> None:
        if ai_system.owner_id != principal.user_id and not principal.is_admin:
            raise ApplicationError(
                ErrorKind.FORBIDDEN,
                "Only the AI system owner or an administrator can change this inventory",
            )

    @staticmethod
    def _require_mutable(ai_system: AISystem) -> None:
        if ai_system.status not in MUTABLE_SYSTEM_STATUSES:
            raise ApplicationError(
                ErrorKind.CONFLICT,
                "AI system is not active for inventory changes",
            )

    @staticmethod
    def _require_version(current: int, expected: int) -> None:
        if current != expected:
            raise ApplicationError(ErrorKind.CONFLICT, "Version conflict")

    @staticmethod
    def _require_not_retired(current: EntityStatus, entity_name: str) -> None:
        if current is EntityStatus.RETIRED:
            raise ApplicationError(ErrorKind.CONFLICT, f"{entity_name} is retired")

    @staticmethod
    def _validate_allowed_models(ai_system: AISystem, allowed_models: list[str]) -> None:
        registered = {
            model.id for model in ai_system.models if model.status is not EntityStatus.RETIRED
        }
        unknown = sorted(set(allowed_models) - registered)
        if unknown:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                {
                    "message": "Agent references models outside the active system inventory",
                    "model_ids": unknown,
                },
            )

    @staticmethod
    def _model_review_candidate(model: ModelAsset) -> ModelReviewCandidate:
        """Map persistence state into a framework-independent model scope."""
        return ModelReviewCandidate(
            provider=model.provider,
            model_name=model.model_name,
            model_version=model.model_version,
            routing_group=model.routing_group,
            deployment_region=model.deployment_region,
            approved_use_cases=tuple(model.approved_use_cases),
            prohibited_use_cases=tuple(model.prohibited_use_cases),
            allowed_data_classes=tuple(model.allowed_data_classes),
            evaluation_baseline=model.evaluation_baseline,
            deprecation_date=(
                InventoryService._as_utc(model.deprecation_date)
                if model.deprecation_date is not None
                else None
            ),
        )

    @staticmethod
    def _agent_review_candidate(agent: Agent) -> AgentReviewCandidate:
        """Map persistence state into a framework-independent agent scope."""
        return AgentReviewCandidate(
            name=agent.name,
            purpose=agent.purpose,
            owner_id=agent.owner_id,
            agent_version=agent.agent_version,
            deployment_region=agent.deployment_region,
            autonomy_level=agent.autonomy_level,
            allowed_models=tuple(agent.allowed_models),
            tools=tuple(agent.tools),
            permissions=tuple(agent.permissions),
            max_cost=agent.max_cost,
            max_runtime_seconds=agent.max_runtime_seconds,
            human_approval_points=tuple(agent.human_approval_points),
            kill_switch_enabled=agent.kill_switch_enabled,
        )

    @staticmethod
    def _review_context(
        ai_system: AISystem,
        principal: Principal,
        *,
        reviewed_at: datetime,
        request: AssetReviewRequest,
        additional_owner_ids: frozenset[str] = frozenset(),
    ) -> AssetReviewContext:
        """Build an independent review context from trusted identity and system risk."""
        return AssetReviewContext(
            reviewer_id=principal.user_id,
            reviewer_areas=principal.approval_areas,
            owner_ids=frozenset({ai_system.owner_id}) | additional_owner_ids,
            risk_tier=ai_system.risk_tier,
            reviewed_at=reviewed_at,
            next_review_at=request.next_review_at,
            reference=request.reference,
        )

    @staticmethod
    def _apply_review_decision(
        asset: ModelAsset | Agent,
        decision: AssetReviewDecision,
    ) -> None:
        """Project a trusted domain decision into the mutable persistence entity."""
        asset.status = EntityStatus.APPROVED
        asset.approved_scope_digest = decision.approved_scope_digest
        asset.reviewed_by = decision.reviewed_by
        asset.reviewed_at = decision.reviewed_at
        asset.next_review_at = decision.next_review_at
        asset.review_reference = decision.review_reference

    @staticmethod
    def _clear_asset_review(asset: ModelAsset | Agent) -> bool:
        """Invalidate current review evidence and return whether state changed."""
        had_review = (
            asset.approved_scope_digest is not None
            or asset.status is EntityStatus.APPROVED
        )
        if not had_review:
            return False
        asset.approved_scope_digest = None
        asset.reviewed_by = None
        asset.reviewed_at = None
        asset.next_review_at = None
        asset.review_reference = None
        if asset.status is not EntityStatus.RETIRED:
            asset.status = EntityStatus.DRAFT
        return True

    @staticmethod
    def _require_current_approved_models(
        ai_system: AISystem,
        allowed_models: list[str],
        *,
        now: datetime,
        agent_next_review_at: datetime,
    ) -> None:
        """Require model approvals to cover the full requested agent review."""
        selected = set(allowed_models)
        unavailable: list[str] = []
        insufficient_validity: list[str] = []
        requested_deadline = InventoryService._as_utc(agent_next_review_at)
        for model in ai_system.models:
            if model.id not in selected:
                continue
            model_deadline = (
                InventoryService._as_utc(model.next_review_at)
                if model.next_review_at is not None
                else None
            )
            if model.status is not EntityStatus.APPROVED or not review_is_current(
                next_review_at=model_deadline,
                now=now,
            ):
                unavailable.append(model.id)
            elif model_deadline is not None and model_deadline < requested_deadline:
                insufficient_validity.append(model.id)
        registered = {model.id for model in ai_system.models}
        unavailable.extend(sorted(selected - registered))
        if unavailable:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                {
                    "message": "Agent review requires current approved models",
                    "model_ids": unavailable,
                },
            )
        if insufficient_validity:
            raise ApplicationError(
                ErrorKind.UNPROCESSABLE,
                {
                    "message": "Agent review cannot outlive its approved models",
                    "model_ids": sorted(insufficient_validity),
                },
            )

    async def _invalidate_agents_for_model(
        self,
        ai_system: AISystem,
        model_id: str,
        principal: Principal,
        *,
        reason: str,
    ) -> list[str]:
        """Invalidate reviewed agents that depend on a changed or retired model."""
        invalidated: list[str] = []
        for agent in ai_system.agents:
            if model_id not in agent.allowed_models or not self._clear_asset_review(agent):
                continue
            agent.version += 1
            invalidated.append(agent.id)
            await self._record_event(
                principal=principal,
                action="agent.review_invalidated",
                entity_type="agent",
                entity_id=agent.id,
                entity_version=agent.version,
                initiative_id=ai_system.initiative_id,
                ai_system_id=ai_system.id,
                extra={
                    "reason": reason,
                    "dependency_type": "model_asset",
                    "dependency_id": model_id,
                },
            )
        return invalidated

    async def _invalidate_system_asset_reviews(
        self,
        ai_system: AISystem,
        principal: Principal,
        *,
        reason: str,
    ) -> int:
        """Invalidate reviewed assets when their system accountability changes."""
        invalidated = 0
        assets: list[ModelAsset | Agent] = [*ai_system.models, *ai_system.agents]
        for asset in assets:
            if not self._clear_asset_review(asset):
                continue
            asset.version += 1
            invalidated += 1
            entity_type = "model_asset" if isinstance(asset, ModelAsset) else "agent"
            action_prefix = "model" if isinstance(asset, ModelAsset) else "agent"
            await self._record_event(
                principal=principal,
                action=f"{action_prefix}.review_invalidated",
                entity_type=entity_type,
                entity_id=asset.id,
                entity_version=asset.version,
                initiative_id=ai_system.initiative_id,
                ai_system_id=ai_system.id,
                extra={"reason": reason},
            )
        return invalidated

    async def _record_review_event(
        self,
        asset: ModelAsset | Agent,
        ai_system: AISystem,
        principal: Principal,
        decision: AssetReviewDecision,
    ) -> None:
        """Append content-minimized evidence for an approved asset scope."""
        await self._record_event(
            principal=principal,
            action=f"{decision.kind.value}.reviewed",
            entity_type=(
                "model_asset" if isinstance(asset, ModelAsset) else "agent"
            ),
            entity_id=asset.id,
            entity_version=asset.version,
            initiative_id=ai_system.initiative_id,
            ai_system_id=ai_system.id,
            extra={
                "approved_scope_digest": decision.approved_scope_digest,
                "reviewer_area": decision.reviewer_area.value,
                "review_reference": decision.review_reference,
                "reviewed_at": decision.reviewed_at.isoformat(),
                "next_review_at": decision.next_review_at.isoformat(),
            },
        )

    @staticmethod
    def _raise_asset_review_error(error: AssetReviewError) -> NoReturn:
        """Map domain review failures to stable application error categories."""
        kind = (
            ErrorKind.FORBIDDEN
            if isinstance(error, AssetReviewForbidden)
            else ErrorKind.UNPROCESSABLE
        )
        raise ApplicationError(kind, str(error)) from error

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        """Normalize SQLite-naive timestamps while preserving real instants."""
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    async def _record_event(
        self,
        *,
        principal: Principal,
        action: str,
        entity_type: str,
        entity_id: str,
        entity_version: int,
        initiative_id: str,
        ai_system_id: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "initiative_id": initiative_id,
            "ai_system_id": ai_system_id,
        }
        payload.update(extra or {})
        await append_audit_event(
            self._session,
            actor_id=principal.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_version=entity_version,
            payload=payload,
        )

    async def _record_cascade_events(
        self,
        ai_system: AISystem,
        principal: Principal,
        retired_models: list[str],
        retired_agents: list[str],
        reason_sha256: str,
    ) -> None:
        for model in ai_system.models:
            if model.id in retired_models:
                await self._record_event(
                    principal=principal,
                    action="model.retired",
                    entity_type="model_asset",
                    entity_id=model.id,
                    entity_version=model.version,
                    initiative_id=ai_system.initiative_id,
                    ai_system_id=ai_system.id,
                    extra={"reason_sha256": reason_sha256, "cascade": True},
                )
        for agent in ai_system.agents:
            if agent.id in retired_agents:
                await self._record_event(
                    principal=principal,
                    action="agent.retired",
                    entity_type="agent",
                    entity_id=agent.id,
                    entity_version=agent.version,
                    initiative_id=ai_system.initiative_id,
                    ai_system_id=ai_system.id,
                    extra={"reason_sha256": reason_sha256, "cascade": True},
                )

    @staticmethod
    def _retire_entities(entities: list[ModelAsset] | list[Agent]) -> list[str]:
        retired: list[str] = []
        for entity in entities:
            if entity.status is not EntityStatus.RETIRED:
                entity.status = EntityStatus.RETIRED
                entity.version += 1
                retired.append(entity.id)
        return retired

    @staticmethod
    def _apply_changes(target: object, changes: dict[str, Any]) -> None:
        for field, value in changes.items():
            setattr(target, field, value)

    @staticmethod
    def _reason_digest(reason: str) -> str:
        return hashlib.sha256(reason.encode()).hexdigest()

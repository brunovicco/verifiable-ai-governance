"""Application service for the operational AI inventory."""

import hashlib
from typing import Any, cast

from governance_schemas import EntityStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_governance_api.audit import append_audit_event
from ai_governance_api.auth import Principal
from ai_governance_api.errors import ApplicationError, ErrorKind
from ai_governance_api.models import Agent, AISystem, AuditEvent, Initiative, ModelAsset
from ai_governance_api.schemas import (
    AgentCreate,
    AgentUpdate,
    AISystemCreate,
    AISystemUpdate,
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

    async def update_system(
        self,
        system_id: str,
        request: AISystemUpdate,
        principal: Principal,
    ) -> AISystem:
        """Update a mutable AI system using optimistic concurrency."""
        ai_system = await self.get_system(system_id)
        self._require_owner(ai_system, principal)
        self._require_mutable(ai_system)
        self._require_version(ai_system.version, request.expected_version)

        changes = request.model_dump(mode="json", exclude_unset=True, exclude={"expected_version"})
        self._apply_changes(ai_system, changes)
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
            extra={"changed_fields": sorted(changes)},
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
        ai_system = await self.get_system(system_id)
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
        ai_system = await self.get_system(system_id)
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
        model = await self._load_model(model_id)
        ai_system = await self.get_system(model.ai_system_id)
        self._require_owner(ai_system, principal)
        self._require_mutable(ai_system)
        self._require_not_retired(model.status, "Model")
        self._require_version(model.version, request.expected_version)
        changes = request.model_dump(exclude_unset=True, exclude={"expected_version"})
        self._apply_changes(model, changes)
        model.version += 1
        await self._session.flush()
        await self._record_event(
            principal=principal,
            action="model.updated",
            entity_type="model_asset",
            entity_id=model.id,
            entity_version=model.version,
            initiative_id=ai_system.initiative_id,
            ai_system_id=ai_system.id,
            extra={"changed_fields": sorted(changes)},
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
        model = await self._load_model(model_id)
        ai_system = await self.get_system(model.ai_system_id)
        self._require_owner(ai_system, principal)
        self._require_mutable(ai_system)
        self._require_not_retired(model.status, "Model")
        self._require_version(model.version, request.expected_version)
        model.status = EntityStatus.RETIRED
        model.version += 1
        await self._session.flush()
        await self._record_event(
            principal=principal,
            action="model.retired",
            entity_type="model_asset",
            entity_id=model.id,
            entity_version=model.version,
            initiative_id=ai_system.initiative_id,
            ai_system_id=ai_system.id,
            extra={"reason_sha256": self._reason_digest(request.reason)},
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
        ai_system = await self.get_system(system_id)
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
        agent = await self._load_agent(agent_id)
        ai_system = await self.get_system(agent.ai_system_id)
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
            extra={"changed_fields": sorted(changes)},
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
        agent = await self._load_agent(agent_id)
        ai_system = await self.get_system(agent.ai_system_id)
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

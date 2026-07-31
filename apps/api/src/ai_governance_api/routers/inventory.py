import hashlib
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from governance_schemas import EntityStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_governance_api.audit import append_audit_event
from ai_governance_api.auth import Principal, get_principal
from ai_governance_api.database import get_db
from ai_governance_api.models import Agent, AISystem, AuditEvent, Initiative, ModelAsset
from ai_governance_api.schemas import (
    AgentCreate,
    AgentRead,
    AgentUpdate,
    AISystemCreate,
    AISystemDetail,
    AISystemRead,
    AISystemUpdate,
    AuditEventRead,
    ModelAssetCreate,
    ModelAssetRead,
    ModelAssetUpdate,
    RetirementRequest,
)

router = APIRouter(prefix="/api/v1", tags=["inventory"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
MUTABLE_SYSTEM_STATUSES = {EntityStatus.APPROVED, EntityStatus.ACTIVE}


async def _load_initiative(session: AsyncSession, initiative_id: str) -> Initiative:
    initiative = await session.get(Initiative, initiative_id)
    if initiative is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Initiative not found")
    return initiative


async def _load_system(session: AsyncSession, system_id: str) -> AISystem:
    ai_system = await session.scalar(
        select(AISystem)
        .where(AISystem.id == system_id)
        .options(selectinload(AISystem.models), selectinload(AISystem.agents))
    )
    if ai_system is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
    return ai_system


async def _load_model(session: AsyncSession, model_id: str) -> ModelAsset:
    model = await session.get(ModelAsset, model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return model


async def _load_agent(session: AsyncSession, agent_id: str) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


def _require_owner(ai_system: AISystem, principal: Principal) -> None:
    if ai_system.owner_id != principal.user_id and not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the AI system owner or an administrator can change this inventory",
        )


def _require_mutable(ai_system: AISystem) -> None:
    if ai_system.status not in MUTABLE_SYSTEM_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AI system is not active for inventory changes",
        )


def _require_version(current: int, expected: int) -> None:
    if current != expected:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version conflict")


def _validate_allowed_models(ai_system: AISystem, allowed_models: list[str]) -> None:
    registered = {
        model.id for model in ai_system.models if model.status is not EntityStatus.RETIRED
    }
    unknown = sorted(set(allowed_models) - registered)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "Agent references models outside the active system inventory",
                "model_ids": unknown,
            },
        )


async def _record_event(
    session: AsyncSession,
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
        session,
        actor_id=principal.user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_version=entity_version,
        payload=payload,
    )


@router.post(
    "/initiatives/{initiative_id}/systems",
    response_model=AISystemDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_ai_system(
    initiative_id: str,
    request: AISystemCreate,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> AISystem:
    initiative = await _load_initiative(session, initiative_id)
    if initiative.status is not EntityStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only an approved initiative can create an AI system",
        )
    if initiative.business_owner_id != principal.user_id and not principal.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the initiative owner or an administrator can create the AI system",
        )

    values = request.model_dump(exclude={"owner_id"})
    ai_system = AISystem(
        **values,
        initiative_id=initiative.id,
        owner_id=request.owner_id or principal.user_id,
        risk_tier=initiative.risk_tier,
        status=EntityStatus.ACTIVE if request.production else EntityStatus.APPROVED,
    )
    session.add(ai_system)
    await session.flush()
    await _record_event(
        session,
        principal=principal,
        action="ai_system.created",
        entity_type="ai_system",
        entity_id=ai_system.id,
        entity_version=ai_system.version,
        initiative_id=initiative.id,
        ai_system_id=ai_system.id,
        extra={"owner_id": ai_system.owner_id, "production": ai_system.production},
    )
    await session.commit()
    return await _load_system(session, ai_system.id)


@router.get("/systems", response_model=list[AISystemRead])
async def list_ai_systems(
    session: DatabaseSession,
    _: CurrentPrincipal,
) -> list[AISystem]:
    result = await session.scalars(select(AISystem).order_by(AISystem.created_at.desc()))
    return list(result)


@router.get("/systems/{system_id}", response_model=AISystemDetail)
async def get_ai_system(
    system_id: str,
    session: DatabaseSession,
    _: CurrentPrincipal,
) -> AISystem:
    return await _load_system(session, system_id)


@router.patch("/systems/{system_id}", response_model=AISystemDetail)
async def update_ai_system(
    system_id: str,
    request: AISystemUpdate,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> AISystem:
    ai_system = await _load_system(session, system_id)
    _require_owner(ai_system, principal)
    _require_mutable(ai_system)
    _require_version(ai_system.version, request.expected_version)

    changes = request.model_dump(mode="json", exclude_unset=True, exclude={"expected_version"})
    for field, value in changes.items():
        setattr(ai_system, field, value)
    if "production" in changes:
        ai_system.status = EntityStatus.ACTIVE if ai_system.production else EntityStatus.APPROVED
    ai_system.version += 1
    await session.flush()
    await _record_event(
        session,
        principal=principal,
        action="ai_system.updated",
        entity_type="ai_system",
        entity_id=ai_system.id,
        entity_version=ai_system.version,
        initiative_id=ai_system.initiative_id,
        ai_system_id=ai_system.id,
        extra={"changed_fields": sorted(changes)},
    )
    await session.commit()
    return await _load_system(session, ai_system.id)


@router.post("/systems/{system_id}/retire", response_model=AISystemDetail)
async def retire_ai_system(
    system_id: str,
    request: RetirementRequest,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> AISystem:
    ai_system = await _load_system(session, system_id)
    _require_owner(ai_system, principal)
    _require_mutable(ai_system)
    _require_version(ai_system.version, request.expected_version)

    retired_models: list[str] = []
    retired_agents: list[str] = []
    for model in ai_system.models:
        if model.status is not EntityStatus.RETIRED:
            model.status = EntityStatus.RETIRED
            model.version += 1
            retired_models.append(model.id)
    for agent in ai_system.agents:
        if agent.status is not EntityStatus.RETIRED:
            agent.status = EntityStatus.RETIRED
            agent.version += 1
            retired_agents.append(agent.id)
    ai_system.status = EntityStatus.RETIRED
    ai_system.production = False
    ai_system.version += 1
    await session.flush()
    reason_sha256 = hashlib.sha256(request.reason.encode()).hexdigest()
    for model in ai_system.models:
        if model.id in retired_models:
            await _record_event(
                session,
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
            await _record_event(
                session,
                principal=principal,
                action="agent.retired",
                entity_type="agent",
                entity_id=agent.id,
                entity_version=agent.version,
                initiative_id=ai_system.initiative_id,
                ai_system_id=ai_system.id,
                extra={"reason_sha256": reason_sha256, "cascade": True},
            )
    await _record_event(
        session,
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
    await session.commit()
    return await _load_system(session, ai_system.id)


@router.post(
    "/systems/{system_id}/models",
    response_model=ModelAssetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_model(
    system_id: str,
    request: ModelAssetCreate,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> ModelAsset:
    ai_system = await _load_system(session, system_id)
    _require_owner(ai_system, principal)
    _require_mutable(ai_system)
    model = ModelAsset(
        **request.model_dump(),
        ai_system_id=ai_system.id,
        status=EntityStatus.DRAFT,
    )
    session.add(model)
    await session.flush()
    await _record_event(
        session,
        principal=principal,
        action="model.created",
        entity_type="model_asset",
        entity_id=model.id,
        entity_version=model.version,
        initiative_id=ai_system.initiative_id,
        ai_system_id=ai_system.id,
        extra={"provider": model.provider, "deployment_region": model.deployment_region},
    )
    await session.commit()
    return model


@router.patch("/models/{model_id}", response_model=ModelAssetRead)
async def update_model(
    model_id: str,
    request: ModelAssetUpdate,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> ModelAsset:
    model = await _load_model(session, model_id)
    ai_system = await _load_system(session, model.ai_system_id)
    _require_owner(ai_system, principal)
    _require_mutable(ai_system)
    if model.status is EntityStatus.RETIRED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Model is retired")
    _require_version(model.version, request.expected_version)
    changes = request.model_dump(exclude_unset=True, exclude={"expected_version"})
    for field, value in changes.items():
        setattr(model, field, value)
    model.version += 1
    await session.flush()
    await _record_event(
        session,
        principal=principal,
        action="model.updated",
        entity_type="model_asset",
        entity_id=model.id,
        entity_version=model.version,
        initiative_id=ai_system.initiative_id,
        ai_system_id=ai_system.id,
        extra={"changed_fields": sorted(changes)},
    )
    await session.commit()
    return model


@router.post("/models/{model_id}/retire", response_model=ModelAssetRead)
async def retire_model(
    model_id: str,
    request: RetirementRequest,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> ModelAsset:
    model = await _load_model(session, model_id)
    ai_system = await _load_system(session, model.ai_system_id)
    _require_owner(ai_system, principal)
    _require_mutable(ai_system)
    if model.status is EntityStatus.RETIRED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Model is retired")
    _require_version(model.version, request.expected_version)
    model.status = EntityStatus.RETIRED
    model.version += 1
    await session.flush()
    await _record_event(
        session,
        principal=principal,
        action="model.retired",
        entity_type="model_asset",
        entity_id=model.id,
        entity_version=model.version,
        initiative_id=ai_system.initiative_id,
        ai_system_id=ai_system.id,
        extra={"reason_sha256": hashlib.sha256(request.reason.encode()).hexdigest()},
    )
    await session.commit()
    return model


@router.post(
    "/systems/{system_id}/agents",
    response_model=AgentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(
    system_id: str,
    request: AgentCreate,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Agent:
    ai_system = await _load_system(session, system_id)
    _require_owner(ai_system, principal)
    _require_mutable(ai_system)
    _validate_allowed_models(ai_system, request.allowed_models)
    values = request.model_dump(exclude={"owner_id"})
    agent = Agent(
        **values,
        ai_system_id=ai_system.id,
        owner_id=request.owner_id or principal.user_id,
        status=EntityStatus.DRAFT,
    )
    session.add(agent)
    await session.flush()
    await _record_event(
        session,
        principal=principal,
        action="agent.created",
        entity_type="agent",
        entity_id=agent.id,
        entity_version=agent.version,
        initiative_id=ai_system.initiative_id,
        ai_system_id=ai_system.id,
        extra={"owner_id": agent.owner_id, "autonomy_level": agent.autonomy_level.value},
    )
    await session.commit()
    return agent


@router.patch("/agents/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: str,
    request: AgentUpdate,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Agent:
    agent = await _load_agent(session, agent_id)
    ai_system = await _load_system(session, agent.ai_system_id)
    _require_owner(ai_system, principal)
    _require_mutable(ai_system)
    if agent.status is EntityStatus.RETIRED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent is retired")
    _require_version(agent.version, request.expected_version)
    changes = request.model_dump(exclude_unset=True, exclude={"expected_version"})
    if "allowed_models" in changes:
        _validate_allowed_models(ai_system, changes["allowed_models"])
    for field, value in changes.items():
        setattr(agent, field, value)
    agent.version += 1
    await session.flush()
    await _record_event(
        session,
        principal=principal,
        action="agent.updated",
        entity_type="agent",
        entity_id=agent.id,
        entity_version=agent.version,
        initiative_id=ai_system.initiative_id,
        ai_system_id=ai_system.id,
        extra={"changed_fields": sorted(changes)},
    )
    await session.commit()
    return agent


@router.post("/agents/{agent_id}/retire", response_model=AgentRead)
async def retire_agent(
    agent_id: str,
    request: RetirementRequest,
    session: DatabaseSession,
    principal: CurrentPrincipal,
) -> Agent:
    agent = await _load_agent(session, agent_id)
    ai_system = await _load_system(session, agent.ai_system_id)
    _require_owner(ai_system, principal)
    _require_mutable(ai_system)
    if agent.status is EntityStatus.RETIRED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent is retired")
    _require_version(agent.version, request.expected_version)
    agent.status = EntityStatus.RETIRED
    agent.version += 1
    await session.flush()
    await _record_event(
        session,
        principal=principal,
        action="agent.retired",
        entity_type="agent",
        entity_id=agent.id,
        entity_version=agent.version,
        initiative_id=ai_system.initiative_id,
        ai_system_id=ai_system.id,
        extra={"reason_sha256": hashlib.sha256(request.reason.encode()).hexdigest()},
    )
    await session.commit()
    return agent


@router.get("/{entity_type}/{entity_id}/audit", response_model=list[AuditEventRead])
async def list_inventory_audit_events(
    entity_type: str,
    entity_id: str,
    session: DatabaseSession,
    _: CurrentPrincipal,
) -> list[AuditEvent]:
    allowed_types = {"systems": "ai_system", "models": "model_asset", "agents": "agent"}
    normalized_type = allowed_types.get(entity_type)
    if normalized_type is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity type not found")
    if normalized_type == "ai_system":
        await _load_system(session, entity_id)
    elif normalized_type == "model_asset":
        await _load_model(session, entity_id)
    else:
        await _load_agent(session, entity_id)
    events = await session.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_type == normalized_type, AuditEvent.entity_id == entity_id)
        .order_by(AuditEvent.occurred_at)
    )
    return list(events)

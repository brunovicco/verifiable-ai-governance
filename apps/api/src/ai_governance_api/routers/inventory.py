"""HTTP adapter for operational inventory use cases."""

from fastapi import APIRouter, status

from ai_governance_api.dependencies import (
    CurrentAuthorizedPrincipal,
    CurrentPrincipal,
    InventoryServiceDependency,
)
from ai_governance_api.models import Agent, AISystem, AuditEvent, ModelAsset
from ai_governance_api.schemas import (
    AgentCreate,
    AgentRead,
    AgentUpdate,
    AISystemCreate,
    AISystemDetail,
    AISystemRead,
    AISystemUpdate,
    AssetReviewRequest,
    AuditEventRead,
    ModelAssetCreate,
    ModelAssetRead,
    ModelAssetUpdate,
    RetirementRequest,
)

router = APIRouter(prefix="/api/v1", tags=["inventory"])


@router.post(
    "/initiatives/{initiative_id}/systems",
    response_model=AISystemDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_ai_system(
    initiative_id: str,
    request: AISystemCreate,
    service: InventoryServiceDependency,
    principal: CurrentPrincipal,
) -> AISystem:
    """Create an AI system for an approved initiative."""
    return await service.create_system(initiative_id, request, principal)


@router.get("/systems", response_model=list[AISystemRead])
async def list_ai_systems(
    service: InventoryServiceDependency,
    _: CurrentPrincipal,
) -> list[AISystem]:
    """List registered AI systems."""
    return await service.list_systems()


@router.get("/systems/{system_id}", response_model=AISystemDetail)
async def get_ai_system(
    system_id: str,
    service: InventoryServiceDependency,
    _: CurrentPrincipal,
) -> AISystem:
    """Return an AI system with its models and agents."""
    return await service.get_system(system_id)


@router.patch("/systems/{system_id}", response_model=AISystemDetail)
async def update_ai_system(
    system_id: str,
    request: AISystemUpdate,
    service: InventoryServiceDependency,
    principal: CurrentPrincipal,
) -> AISystem:
    """Update an AI system using optimistic concurrency."""
    return await service.update_system(system_id, request, principal)


@router.post("/systems/{system_id}/retire", response_model=AISystemDetail)
async def retire_ai_system(
    system_id: str,
    request: RetirementRequest,
    service: InventoryServiceDependency,
    principal: CurrentPrincipal,
) -> AISystem:
    """Retire an AI system and its active inventory."""
    return await service.retire_system(system_id, request, principal)


@router.post(
    "/systems/{system_id}/models",
    response_model=ModelAssetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_model(
    system_id: str,
    request: ModelAssetCreate,
    service: InventoryServiceDependency,
    principal: CurrentPrincipal,
) -> ModelAsset:
    """Register a model in an AI system."""
    return await service.create_model(system_id, request, principal)


@router.patch("/models/{model_id}", response_model=ModelAssetRead)
async def update_model(
    model_id: str,
    request: ModelAssetUpdate,
    service: InventoryServiceDependency,
    principal: CurrentPrincipal,
) -> ModelAsset:
    """Update a registered model."""
    return await service.update_model(model_id, request, principal)


@router.post("/models/{model_id}/review", response_model=ModelAssetRead)
async def review_model(
    model_id: str,
    request: AssetReviewRequest,
    service: InventoryServiceDependency,
    principal: CurrentAuthorizedPrincipal,
) -> ModelAsset:
    """Approve one model scope through an independent architecture review."""
    return await service.review_model(model_id, request, principal)


@router.post("/models/{model_id}/retire", response_model=ModelAssetRead)
async def retire_model(
    model_id: str,
    request: RetirementRequest,
    service: InventoryServiceDependency,
    principal: CurrentPrincipal,
) -> ModelAsset:
    """Retire a registered model."""
    return await service.retire_model(model_id, request, principal)


@router.post(
    "/systems/{system_id}/agents",
    response_model=AgentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(
    system_id: str,
    request: AgentCreate,
    service: InventoryServiceDependency,
    principal: CurrentPrincipal,
) -> Agent:
    """Register an agent in an AI system."""
    return await service.create_agent(system_id, request, principal)


@router.patch("/agents/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: str,
    request: AgentUpdate,
    service: InventoryServiceDependency,
    principal: CurrentPrincipal,
) -> Agent:
    """Update a registered agent."""
    return await service.update_agent(agent_id, request, principal)


@router.post("/agents/{agent_id}/review", response_model=AgentRead)
async def review_agent(
    agent_id: str,
    request: AssetReviewRequest,
    service: InventoryServiceDependency,
    principal: CurrentAuthorizedPrincipal,
) -> Agent:
    """Approve one agent scope through an independent security review."""
    return await service.review_agent(agent_id, request, principal)


@router.post("/agents/{agent_id}/retire", response_model=AgentRead)
async def retire_agent(
    agent_id: str,
    request: RetirementRequest,
    service: InventoryServiceDependency,
    principal: CurrentPrincipal,
) -> Agent:
    """Retire a registered agent."""
    return await service.retire_agent(agent_id, request, principal)


@router.get("/{entity_type}/{entity_id}/audit", response_model=list[AuditEventRead])
async def list_inventory_audit_events(
    entity_type: str,
    entity_id: str,
    service: InventoryServiceDependency,
    _: CurrentPrincipal,
) -> list[AuditEvent]:
    """Return the audit trail for a supported inventory entity."""
    return await service.list_audit_events(entity_type, entity_id)

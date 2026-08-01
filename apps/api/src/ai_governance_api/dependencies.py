"""FastAPI dependency wiring for application services."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from policy_engine import GovernancePolicyEngine
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.auth import Principal, get_principal
from ai_governance_api.database import get_db
from ai_governance_api.services import InitiativeService, InventoryService, PolicyEvaluator

DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


@lru_cache
def get_policy_evaluator() -> PolicyEvaluator:
    """Return the default stateless policy evaluator."""
    return GovernancePolicyEngine()


PolicyEvaluatorDependency = Annotated[PolicyEvaluator, Depends(get_policy_evaluator)]


def get_initiative_service(
    session: DatabaseSession,
    policy_evaluator: PolicyEvaluatorDependency,
) -> InitiativeService:
    """Build the request-scoped initiative service."""
    return InitiativeService(session, policy_evaluator)


def get_inventory_service(session: DatabaseSession) -> InventoryService:
    """Build the request-scoped inventory service."""
    return InventoryService(session)


InitiativeServiceDependency = Annotated[InitiativeService, Depends(get_initiative_service)]
InventoryServiceDependency = Annotated[InventoryService, Depends(get_inventory_service)]

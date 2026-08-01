"""FastAPI dependency wiring for application services."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from policy_engine import GovernancePolicyEngine
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.adapters import (
    SqlAlchemyAssessmentAudit,
    SqlAlchemyAssessmentStore,
    SqlAlchemyTransaction,
)
from ai_governance_api.application import ListAssessments, SaveAssessment, SubmitAssessment
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


def get_save_assessment(session: DatabaseSession) -> SaveAssessment:
    """Build the request-scoped save-assessment use case at the composition root."""
    return SaveAssessment(
        SqlAlchemyAssessmentStore(session),
        SqlAlchemyAssessmentAudit(session),
        SqlAlchemyTransaction(session),
    )


def get_list_assessments(session: DatabaseSession) -> ListAssessments:
    """Build the request-scoped assessment query at the composition root."""
    return ListAssessments(SqlAlchemyAssessmentStore(session))


def get_submit_assessment(session: DatabaseSession) -> SubmitAssessment:
    """Build the request-scoped submit-assessment use case at the composition root."""
    return SubmitAssessment(
        SqlAlchemyAssessmentStore(session),
        SqlAlchemyAssessmentAudit(session),
        SqlAlchemyTransaction(session),
    )


SaveAssessmentDependency = Annotated[SaveAssessment, Depends(get_save_assessment)]
ListAssessmentsDependency = Annotated[ListAssessments, Depends(get_list_assessments)]
SubmitAssessmentDependency = Annotated[SubmitAssessment, Depends(get_submit_assessment)]

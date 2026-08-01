"""SQLAlchemy adapter for initiative control applicability facts."""

from governance_schemas import ControlContext
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.models import Initiative


class SqlAlchemyInitiativeControlContextStore:
    """Read minimal initiative facts through a request-scoped SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the adapter with its backing-service session."""
        self._session = session

    async def get(self, initiative_id: str) -> ControlContext | None:
        """Map one persistence entity into a framework-independent control context."""
        initiative = await self._session.get(Initiative, initiative_id)
        if initiative is None:
            return None
        return ControlContext(
            decision_impact=initiative.decision_impact,
            data_classification=initiative.data_classification,
            autonomy_level=initiative.autonomy_level,
            hosting_model=initiative.hosting_model,
            risk_tier=initiative.risk_tier,
            affects_rights=initiative.affects_rights,
            executes_actions=initiative.executes_actions,
            personal_data=initiative.personal_data,
            sensitive_data=initiative.sensitive_data,
            children_data=initiative.children_data,
            external_facing=initiative.external_facing,
            regulated_context=initiative.regulated_context,
            international_processing=initiative.international_processing,
            uses_rag=initiative.uses_rag,
            uses_agents=initiative.uses_agents,
            uses_mcp=initiative.uses_mcp,
            uses_custom_model=initiative.uses_custom_model,
        )

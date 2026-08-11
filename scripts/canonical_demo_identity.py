"""Deterministic identities for the canonical governance demo scenario."""

from uuid import UUID, uuid5

from ai_governance_api.models import (
    Agent,
    AISystem,
    Approval,
    Assessment,
    Evidence,
    Initiative,
    ModelAsset,
    ReviewSubmission,
)
from sqlalchemy import event
from sqlalchemy.orm import Session

CANONICAL_DEMO_SCENARIO_ID = "credit-pj-governed-runtime"
CANONICAL_DEMO_NAMESPACE = UUID("a83c529a-257f-4fb5-a7b6-9f611793d9b4")
CANONICAL_DEMO_INITIATIVE_NAME = "[DEMO-CANONICAL] Análise de Crédito PJ Assistida e Auditável"
CANONICAL_DEMO_SYSTEM_NAME = "Mesa de Crédito PJ Governada"
CANONICAL_DEMO_APPROVED_MODEL_NAME = "credit-opinion-approved"
CANONICAL_DEMO_OUT_OF_SCOPE_MODEL_NAME = "credit-opinion-experimental"
CANONICAL_DEMO_AGENT_NAME = "Agente de Parecer de Crédito PJ"


def canonical_demo_id(identity_key: str) -> str:
    """Return the stable UUIDv5 assigned to one semantic demo identity."""
    namespaced_key = f"{CANONICAL_DEMO_SCENARIO_ID}:{identity_key}"
    return str(uuid5(CANONICAL_DEMO_NAMESPACE, namespaced_key))


CANONICAL_DEMO_INITIATIVE_ID = canonical_demo_id("initiative")
CANONICAL_DEMO_SYSTEM_ID = canonical_demo_id("ai-system")
CANONICAL_DEMO_APPROVED_MODEL_ID = canonical_demo_id(f"model:{CANONICAL_DEMO_APPROVED_MODEL_NAME}")
CANONICAL_DEMO_OUT_OF_SCOPE_MODEL_ID = canonical_demo_id(
    f"model:{CANONICAL_DEMO_OUT_OF_SCOPE_MODEL_NAME}"
)
CANONICAL_DEMO_AGENT_ID = canonical_demo_id("agent")


def install_canonical_demo_identity_listener() -> None:
    """Install the idempotent SQLAlchemy hook used only by canonical demo rows."""
    if not event.contains(Session, "before_flush", _assign_canonical_demo_ids):
        event.listen(Session, "before_flush", _assign_canonical_demo_ids)


def _assign_canonical_demo_ids(
    session: Session,
    flush_context: object,
    instances: object | None,
) -> None:
    """Replace generated IDs only for new rows belonging to the canonical demo."""
    del flush_context, instances
    for entity in session.new:
        _assign_canonical_demo_id(entity)


def _assign_canonical_demo_id(entity: object) -> None:
    """Assign one semantic UUID without changing non-demo persistence behavior."""
    if isinstance(entity, Initiative):
        if entity.name == CANONICAL_DEMO_INITIATIVE_NAME:
            entity.id = CANONICAL_DEMO_INITIATIVE_ID
        return

    if isinstance(entity, AISystem):
        if (
            entity.initiative_id == CANONICAL_DEMO_INITIATIVE_ID
            and entity.name == CANONICAL_DEMO_SYSTEM_NAME
        ):
            entity.id = CANONICAL_DEMO_SYSTEM_ID
        return

    if isinstance(entity, ModelAsset):
        if entity.ai_system_id != CANONICAL_DEMO_SYSTEM_ID:
            return
        if entity.model_name == CANONICAL_DEMO_APPROVED_MODEL_NAME:
            entity.id = CANONICAL_DEMO_APPROVED_MODEL_ID
        elif entity.model_name == CANONICAL_DEMO_OUT_OF_SCOPE_MODEL_NAME:
            entity.id = CANONICAL_DEMO_OUT_OF_SCOPE_MODEL_ID
        return

    if isinstance(entity, Agent):
        if (
            entity.ai_system_id == CANONICAL_DEMO_SYSTEM_ID
            and entity.name == CANONICAL_DEMO_AGENT_NAME
        ):
            entity.id = CANONICAL_DEMO_AGENT_ID
        return

    if isinstance(entity, Assessment):
        if entity.initiative_id == CANONICAL_DEMO_INITIATIVE_ID:
            entity.id = canonical_demo_id(f"assessment:{entity.assessment_type}")
        return

    if isinstance(entity, ReviewSubmission):
        if _belongs_to_canonical_initiative(entity):
            entity.id = canonical_demo_id(f"review-submission:{entity.review_round}")
        return

    if isinstance(entity, Approval):
        if _belongs_to_canonical_initiative(entity):
            key = f"approval:{entity.review_round}:{entity.area.value}"
            entity.id = canonical_demo_id(key)
        return

    if (
        isinstance(entity, Evidence)
        and entity.initiative_id == CANONICAL_DEMO_INITIATIVE_ID
        and entity.uri.startswith("urn:demo:")
    ):
        entity.id = canonical_demo_id(f"evidence:{entity.uri}")


def _belongs_to_canonical_initiative(entity: Approval | ReviewSubmission) -> bool:
    """Recognize canonical review rows before or after relationship synchronization."""
    if entity.initiative_id == CANONICAL_DEMO_INITIATIVE_ID:
        return True
    initiative = entity.initiative
    return initiative is not None and initiative.id == CANONICAL_DEMO_INITIATIVE_ID

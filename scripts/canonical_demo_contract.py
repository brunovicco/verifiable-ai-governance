"""Pure deterministic identity contract for the canonical governance demo."""

from uuid import UUID, uuid5

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


def canonical_demo_release_record() -> dict[str, str]:
    """Return the stable top-level canonical identities used by release evidence."""
    return {
        "scenario_id": CANONICAL_DEMO_SCENARIO_ID,
        "identity_scheme": "uuidv5",
        "initiative_id": CANONICAL_DEMO_INITIATIVE_ID,
        "ai_system_id": CANONICAL_DEMO_SYSTEM_ID,
        "approved_model_id": CANONICAL_DEMO_APPROVED_MODEL_ID,
        "out_of_scope_model_id": CANONICAL_DEMO_OUT_OF_SCOPE_MODEL_ID,
        "agent_id": CANONICAL_DEMO_AGENT_ID,
    }

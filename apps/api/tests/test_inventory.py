from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

INITIATIVE_OWNER = {"X-User-Id": "initiative-owner"}
SYSTEM_OWNER = {"X-User-Id": "system-owner"}


def initiative_payload() -> dict[str, object]:
    return {
        "name": "Assistente de conhecimento corporativo",
        "description": (
            "Recupera conteúdo interno aprovado sem executar decisões ou ações externas."
        ),
        "business_area": "Operações",
        "intended_users": "Colaboradores da organização",
        "decision_impact": "informational",
        "data_classification": "internal",
        "autonomy_level": "a0_information",
        "hosting_model": "saas",
        "uses_rag": True,
    }


def system_payload() -> dict[str, object]:
    return {
        "name": "Knowledge Assistant",
        "purpose": "Fornecer respostas fundamentadas no conteúdo corporativo aprovado.",
        "owner_id": "system-owner",
        "production": False,
        "metadata_json": {"business_unit": "operations"},
    }


async def create_approved_initiative(client: AsyncClient) -> dict[str, object]:
    created = await client.post(
        "/api/v1/initiatives", json=initiative_payload(), headers=INITIATIVE_OWNER
    )
    assert created.status_code == 201
    submitted = await client.post(
        f"/api/v1/initiatives/{created.json()['id']}/submit",
        json={"expected_version": created.json()["version"]},
        headers=INITIATIVE_OWNER,
    )
    assert submitted.status_code == 200
    for approval in submitted.json()["approvals"]:
        if not approval["required"]:
            continue
        decided = await client.post(
            f"/api/v1/initiatives/{created.json()['id']}/approvals/{approval['id']}/decision",
            json={
                "decision": "approved",
                "comments": "Finalidade, riscos e accountability foram validados.",
                "evidence_uri": f"urn:test:{approval['area']}-approval",
                "expected_version": approval["version"],
            },
            headers={
                "X-User-Id": f"reviewer-{approval['area']}",
                "X-User-Areas": approval["area"],
            },
        )
        assert decided.status_code == 200
    approved = await client.get(
        f"/api/v1/initiatives/{created.json()['id']}", headers=INITIATIVE_OWNER
    )
    assert approved.json()["status"] == "approved"
    return approved.json()


async def test_system_requires_approved_initiative_and_its_owner(client: AsyncClient) -> None:
    draft = await client.post(
        "/api/v1/initiatives", json=initiative_payload(), headers=INITIATIVE_OWNER
    )
    blocked = await client.post(
        f"/api/v1/initiatives/{draft.json()['id']}/systems",
        json=system_payload(),
        headers=INITIATIVE_OWNER,
    )
    assert blocked.status_code == 409

    approved = await create_approved_initiative(client)
    unauthorized = await client.post(
        f"/api/v1/initiatives/{approved['id']}/systems",
        json=system_payload(),
        headers={"X-User-Id": "unrelated-user"},
    )
    assert unauthorized.status_code == 403


async def test_inventory_lifecycle_is_versioned_authorized_and_audited(
    client: AsyncClient,
) -> None:
    initiative = await create_approved_initiative(client)
    created_system = await client.post(
        f"/api/v1/initiatives/{initiative['id']}/systems",
        json=system_payload(),
        headers=INITIATIVE_OWNER,
    )
    assert created_system.status_code == 201
    ai_system = created_system.json()
    assert ai_system["owner_id"] == "system-owner"
    assert ai_system["status"] == "approved"

    initiative_detail = await client.get(
        f"/api/v1/initiatives/{initiative['id']}", headers=INITIATIVE_OWNER
    )
    assert [item["id"] for item in initiative_detail.json()["systems"]] == [ai_system["id"]]

    forbidden = await client.patch(
        f"/api/v1/systems/{ai_system['id']}",
        json={"production": True, "expected_version": ai_system["version"]},
        headers={"X-User-Id": "unrelated-user"},
    )
    assert forbidden.status_code == 403

    conflict = await client.patch(
        f"/api/v1/systems/{ai_system['id']}",
        json={"production": True, "expected_version": 999},
        headers=SYSTEM_OWNER,
    )
    assert conflict.status_code == 409

    activated = await client.patch(
        f"/api/v1/systems/{ai_system['id']}",
        json={"production": True, "expected_version": ai_system["version"]},
        headers=SYSTEM_OWNER,
    )
    assert activated.status_code == 200
    ai_system = activated.json()
    assert ai_system["status"] == "active"
    assert ai_system["production"] is True

    model_response = await client.post(
        f"/api/v1/systems/{ai_system['id']}/models",
        json={
            "provider": "Example AI",
            "model_name": "governed-medium",
            "model_version": "2026-07-01",
            "deployment_region": "Brazil South",
            "approved_use_cases": ["enterprise knowledge assistance"],
            "prohibited_use_cases": ["automated employment decisions"],
            "allowed_data_classes": ["public", "internal"],
            "evaluation_baseline": {
                "dataset": "enterprise-knowledge-eval-v1",
                "groundedness": 0.92,
            },
        },
        headers=SYSTEM_OWNER,
    )
    assert model_response.status_code == 201
    model = model_response.json()
    assert model["status"] == "draft"
    assert model["review_state"] == "not_reviewed"

    invalid_agent = await client.post(
        f"/api/v1/systems/{ai_system['id']}/agents",
        json={
            "name": "Unbound agent",
            "purpose": "Tenta usar um modelo que não pertence ao inventário do sistema.",
            "agent_version": "1.0.0",
            "deployment_region": "Brazil South",
            "autonomy_level": "a0_information",
            "allowed_models": ["unknown-model"],
        },
        headers=SYSTEM_OWNER,
    )
    assert invalid_agent.status_code == 422

    agent_response = await client.post(
        f"/api/v1/systems/{ai_system['id']}/agents",
        json={
            "name": "Knowledge retrieval agent",
            "purpose": "Recuperar fontes aprovadas e preparar respostas com citações.",
            "owner_id": "agent-owner",
            "agent_version": "1.0.0",
            "deployment_region": "Brazil South",
            "autonomy_level": "a1_recommendation",
            "allowed_models": [model["id"]],
            "tools": ["enterprise-search"],
            "permissions": ["knowledge:read"],
            "max_cost": 0.5,
            "max_runtime_seconds": 30,
            "human_approval_points": ["publication"],
            "kill_switch_enabled": True,
        },
        headers=SYSTEM_OWNER,
    )
    assert agent_response.status_code == 201
    agent = agent_response.json()
    assert agent["status"] == "draft"

    next_review_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    premature_agent_review = await client.post(
        f"/api/v1/agents/{agent['id']}/review",
        json={
            "expected_version": agent["version"],
            "next_review_at": next_review_at,
            "reference": "SEC-2026-184",
        },
        headers={"X-User-Id": "security-reviewer", "X-User-Areas": "security"},
    )
    assert premature_agent_review.status_code == 422

    owner_model_review = await client.post(
        f"/api/v1/models/{model['id']}/review",
        json={
            "expected_version": model["version"],
            "next_review_at": next_review_at,
            "reference": "ARCH-2026-184",
        },
        headers={"X-User-Id": "system-owner", "X-User-Areas": "architecture"},
    )
    assert owner_model_review.status_code == 403

    model_review = await client.post(
        f"/api/v1/models/{model['id']}/review",
        json={
            "expected_version": model["version"],
            "next_review_at": next_review_at,
            "reference": "ARCH-2026-184",
        },
        headers={"X-User-Id": "architecture-reviewer", "X-User-Areas": "architecture"},
    )
    assert model_review.status_code == 200
    model = model_review.json()
    assert model["status"] == "approved"
    assert model["review_state"] == "current"
    assert len(model["approved_scope_digest"]) == 64
    assert model["reviewed_by"] == "architecture-reviewer"

    overlong_agent_review = await client.post(
        f"/api/v1/agents/{agent['id']}/review",
        json={
            "expected_version": agent["version"],
            "next_review_at": (
                datetime.fromisoformat(next_review_at) + timedelta(days=1)
            ).isoformat(),
            "reference": "SEC-2026-184",
        },
        headers={"X-User-Id": "security-reviewer", "X-User-Areas": "security"},
    )
    assert overlong_agent_review.status_code == 422

    agent_review = await client.post(
        f"/api/v1/agents/{agent['id']}/review",
        json={
            "expected_version": agent["version"],
            "next_review_at": next_review_at,
            "reference": "SEC-2026-184",
        },
        headers={"X-User-Id": "security-reviewer", "X-User-Areas": "security"},
    )
    assert agent_review.status_code == 200
    agent = agent_review.json()
    assert agent["status"] == "approved"
    assert agent["review_state"] == "current"
    assert len(agent["approved_scope_digest"]) == 64

    model_conflict = await client.patch(
        f"/api/v1/models/{model['id']}",
        json={"deployment_region": "Brazil Southeast", "expected_version": 999},
        headers=SYSTEM_OWNER,
    )
    assert model_conflict.status_code == 409

    updated_model = await client.patch(
        f"/api/v1/models/{model['id']}",
        json={
            "deployment_region": "Brazil Southeast",
            "expected_version": model["version"],
        },
        headers=SYSTEM_OWNER,
    )
    assert updated_model.status_code == 200
    model = updated_model.json()
    assert model["status"] == "draft"
    assert model["approved_scope_digest"] is None
    assert model["review_state"] == "not_reviewed"

    detail_after_model_change = await client.get(
        f"/api/v1/systems/{ai_system['id']}",
        headers=SYSTEM_OWNER,
    )
    agent = detail_after_model_change.json()["agents"][0]
    assert agent["status"] == "draft"
    assert agent["approved_scope_digest"] is None

    updated_agent = await client.patch(
        f"/api/v1/agents/{agent['id']}",
        json={
            "tools": ["enterprise-search", "citation-check"],
            "expected_version": agent["version"],
        },
        headers=SYSTEM_OWNER,
    )
    assert updated_agent.status_code == 200
    agent = updated_agent.json()

    detail = await client.get(f"/api/v1/systems/{ai_system['id']}", headers=SYSTEM_OWNER)
    assert detail.status_code == 200
    assert [item["id"] for item in detail.json()["models"]] == [model["id"]]
    assert [item["id"] for item in detail.json()["agents"]] == [agent["id"]]

    model_audit = await client.get(f"/api/v1/models/{model['id']}/audit", headers=SYSTEM_OWNER)
    assert [event["action"] for event in model_audit.json()] == [
        "model.created",
        "model.reviewed",
        "model.updated",
    ]

    agent_audit = await client.get(f"/api/v1/agents/{agent['id']}/audit", headers=SYSTEM_OWNER)
    assert [event["action"] for event in agent_audit.json()] == [
        "agent.created",
        "agent.reviewed",
        "agent.review_invalidated",
        "agent.updated",
    ]

    retired_system = await client.post(
        f"/api/v1/systems/{ai_system['id']}/retire",
        json={
            "expected_version": ai_system["version"],
            "reason": "Solução substituída por um serviço corporativo consolidado.",
        },
        headers=SYSTEM_OWNER,
    )
    assert retired_system.status_code == 200
    retired = retired_system.json()
    assert retired["status"] == "retired"
    assert retired["production"] is False
    assert retired["models"][0]["status"] == "retired"
    assert retired["agents"][0]["status"] == "retired"

    cascaded_model_audit = await client.get(
        f"/api/v1/models/{model['id']}/audit", headers=SYSTEM_OWNER
    )
    assert cascaded_model_audit.json()[-1]["action"] == "model.retired"
    assert cascaded_model_audit.json()[-1]["payload"]["cascade"] is True

    blocked_model = await client.post(
        f"/api/v1/systems/{ai_system['id']}/models",
        json={
            "provider": "Example AI",
            "model_name": "late-model",
            "model_version": "1",
            "deployment_region": "Brazil South",
        },
        headers=SYSTEM_OWNER,
    )
    assert blocked_model.status_code == 409

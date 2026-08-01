from typing import Any

from httpx import AsyncClient

OWNER_HEADERS = {"X-User-Id": "control-owner"}


def high_risk_initiative_payload() -> dict[str, Any]:
    return {
        "name": "Agente regulado internacional",
        "description": "Executa ações materiais com dados restritos e revisão humana.",
        "business_area": "Operações",
        "intended_users": "Analistas de operações reguladas",
        "decision_impact": "rights_or_safety",
        "data_classification": "restricted",
        "autonomy_level": "a4_high_impact_actions",
        "hosting_model": "hybrid",
        "affects_rights": True,
        "executes_actions": True,
        "personal_data": True,
        "sensitive_data": True,
        "external_facing": True,
        "regulated_context": True,
        "international_processing": True,
        "inference_countries": ["Estados Unidos"],
        "uses_rag": True,
        "uses_agents": True,
        "uses_mcp": True,
        "uses_custom_model": True,
    }


async def test_catalog_endpoint_returns_versioned_25_controls(client: AsyncClient) -> None:
    response = await client.get("/api/v1/controls", headers=OWNER_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["catalog_id"] == "verifiable-ai-governance-baseline"
    assert body["version"] == "1.0.0"
    assert len(body["controls"]) == 25
    assert len({control["control_id"] for control in body["controls"]}) == 25


async def test_initiative_report_explains_control_applicability(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/initiatives",
        json=high_risk_initiative_payload(),
        headers=OWNER_HEADERS,
    )
    initiative_id = created.json()["id"]

    response = await client.get(
        f"/api/v1/initiatives/{initiative_id}/controls",
        headers=OWNER_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["initiative_id"] == initiative_id
    assert body["catalog_version"] == "1.0.0"
    assert len(body["controls"]) == 25
    assert all(item["applicable"] for item in body["controls"])
    agent_control = next(
        item for item in body["controls"] if item["control"]["control_id"] == "GOV-AGT-001"
    )
    assert "uses_agents" in " ".join(agent_control["reasons"])


async def test_initiative_control_report_fails_closed_for_unknown_id(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/initiatives/unknown/controls",
        headers=OWNER_HEADERS,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Initiative not found"}

from ai_governance_api.dependencies import get_authorized_principal
from ai_governance_api.domain.identity import AuthorizationProvenance, Principal
from ai_governance_api.main import app
from governance_schemas import ApprovalArea
from httpx import AsyncClient

OWNER_HEADERS = {"X-User-Id": "owner-1"}


def low_risk_payload() -> dict[str, object]:
    return {
        "name": "Assistente de conteúdo interno",
        "description": "Auxilia a redação de textos não sensíveis sem executar decisões ou ações.",
        "business_area": "Comunicação",
        "intended_users": "Equipe interna de comunicação",
        "decision_impact": "informational",
        "data_classification": "public",
        "autonomy_level": "a0_information",
        "hosting_model": "saas",
    }


async def test_create_submit_and_approve_low_risk_initiative(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/initiatives", json=low_risk_payload(), headers=OWNER_HEADERS
    )
    assert created.status_code == 201
    initiative = created.json()
    assert initiative["risk_tier"] == "low"

    submitted = await client.post(
        f"/api/v1/initiatives/{initiative['id']}/submit",
        json={"expected_version": initiative["version"]},
        headers=OWNER_HEADERS,
    )
    assert submitted.status_code == 200
    submitted_body = submitted.json()
    assert len(submitted_body["approvals"]) == 9
    required = [item for item in submitted_body["approvals"] if item["required"]]
    assert [item["area"] for item in required] == ["business"]

    approval = required[0]
    self_approval = await client.post(
        f"/api/v1/initiatives/{initiative['id']}/approvals/{approval['id']}/decision",
        json={
            "decision": "approved",
            "comments": "Aprovado pelo owner, o que não deveria ser aceito.",
            "evidence_uri": "urn:test:self-approval",
            "expected_version": approval["version"],
        },
        headers={"X-User-Id": "owner-1", "X-User-Areas": "business"},
    )
    assert self_approval.status_code == 403

    authorized_reviewer = Principal(
        user_id="business-reviewer",
        approval_areas=frozenset({ApprovalArea.BUSINESS}),
        authorization_provenance=AuthorizationProvenance(
            catalog_id="enterprise-entra-authorization",
            catalog_version="2026.08.1",
            catalog_digest="a" * 64,
            matched_mapping_ids=("entra-business-reviewer",),
            source_types=("app_role",),
        ),
    )
    app.dependency_overrides[get_authorized_principal] = lambda: authorized_reviewer
    try:
        approved = await client.post(
            f"/api/v1/initiatives/{initiative['id']}/approvals/{approval['id']}/decision",
            json={
                "decision": "approved",
                "comments": "Finalidade e owner validados com evidência anexada.",
                "evidence_uri": "urn:test:business-review",
                "expected_version": approval["version"],
            },
            headers={"X-User-Id": "business-reviewer"},
        )
    finally:
        app.dependency_overrides.pop(get_authorized_principal, None)
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    audit = await client.get(f"/api/v1/initiatives/{initiative['id']}/audit", headers=OWNER_HEADERS)
    events = audit.json()
    assert [event["action"] for event in events] == [
        "initiative.created",
        "initiative.submitted",
        "approval.decided",
    ]
    assert events[1]["previous_hash"] == events[0]["event_hash"]
    assert events[2]["previous_hash"] == events[1]["event_hash"]
    assert events[2]["payload"]["authorization"] == {
        "catalog_id": "enterprise-entra-authorization",
        "catalog_version": "2026.08.1",
        "catalog_digest": "a" * 64,
        "matched_mapping_ids": ["entra-business-reviewer"],
        "source_types": ["app_role"],
    }


async def test_high_risk_initiative_requires_all_areas(client: AsyncClient) -> None:
    payload = low_risk_payload() | {
        "name": "Agente para operação regulada",
        "description": "Executa operações reversíveis com dados pessoais em processo regulado.",
        "decision_impact": "material",
        "data_classification": "restricted",
        "autonomy_level": "a3_reversible_actions",
        "hosting_model": "hybrid",
        "executes_actions": True,
        "personal_data": True,
        "sensitive_data": True,
        "international_processing": True,
        "inference_countries": ["Estados Unidos"],
        "regulated_context": True,
        "uses_rag": True,
        "uses_agents": True,
        "uses_mcp": True,
        "uses_custom_model": True,
        "external_facing": True,
    }
    created = await client.post("/api/v1/initiatives", json=payload, headers=OWNER_HEADERS)
    assert created.status_code == 201
    submitted = await client.post(
        f"/api/v1/initiatives/{created.json()['id']}/submit",
        json={"expected_version": created.json()["version"]},
        headers=OWNER_HEADERS,
    )

    assert submitted.status_code == 200
    body = submitted.json()
    assert body["risk_tier"] in {"high", "critical"}
    assert all(item["required"] for item in body["approvals"])
    assert "ripd" in body["required_documents"]
    assert "international-processing-assessment" in body["required_documents"]


async def test_submission_fails_closed_on_inconsistent_autonomy(client: AsyncClient) -> None:
    payload = low_risk_payload() | {
        "executes_actions": True,
        "autonomy_level": "a1_recommendation",
    }
    created = await client.post("/api/v1/initiatives", json=payload, headers=OWNER_HEADERS)
    response = await client.post(
        f"/api/v1/initiatives/{created.json()['id']}/submit",
        json={"expected_version": created.json()["version"]},
        headers=OWNER_HEADERS,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["reasons"]

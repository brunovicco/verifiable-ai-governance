"""HTTP integration tests for structured assessment workflows."""

from typing import Any

from httpx import AsyncClient

OWNER_HEADERS = {"X-User-Id": "assessment-owner"}


def initiative_payload(**changes: object) -> dict[str, Any]:
    """Return a proposal that requires privacy and international assessments."""
    payload: dict[str, Any] = {
        "name": "Assistente internacional de atendimento",
        "description": "Apoia atendimento com dados pessoais e processamento internacional.",
        "business_area": "Atendimento",
        "intended_users": "Equipe interna de atendimento",
        "decision_impact": "operational",
        "data_classification": "confidential",
        "autonomy_level": "a1_recommendation",
        "hosting_model": "saas",
        "personal_data": True,
        "international_processing": True,
        "inference_countries": ["United States"],
    }
    payload.update(changes)
    return payload


def impact_payload(expected_version: int | None = None) -> dict[str, Any]:
    """Return a complete versioned AIA request payload."""
    return {
        "expected_version": expected_version,
        "answers": {
            "assessment_type": "ai-impact-assessment",
            "affected_groups": ["customers", "support workers"],
            "intended_benefits": "Improve response consistency and reduce handling time.",
            "potential_harms": ["incorrect guidance", "automation bias"],
            "human_oversight": "Material guidance is escalated to a trained reviewer.",
            "contestability": "Customers can request correction and human review.",
            "mitigation_measures": ["evaluation baseline", "review queue"],
            "residual_risk": "medium",
        },
    }


def ripd_payload() -> dict[str, Any]:
    """Return a complete RIPD request payload."""
    return {
        "answers": {
            "assessment_type": "ripd",
            "controller_area": "Customer Operations",
            "processing_purpose": "Provide contextual assistance to support workers.",
            "personal_data_categories": ["contact data", "support history"],
            "data_subjects": ["customers"],
            "legal_basis": "legitimate interest subject to privacy review",
            "necessity_assessment": "Only recent support context is sent to the model.",
            "risk_scenarios": ["excessive disclosure", "incorrect access"],
            "safeguards": ["least privilege", "retention limits"],
            "residual_risk": "medium",
        }
    }


def international_payload() -> dict[str, Any]:
    """Return a complete cross-border processing request payload."""
    return {
        "answers": {
            "assessment_type": "international-processing-assessment",
            "data_categories": ["support history"],
            "source_country": "Brazil",
            "inference_countries": ["United States"],
            "storage_regions": ["Brazil South"],
            "log_regions": ["United States"],
            "subprocessors": [
                {
                    "name": "Example Cloud",
                    "countries": ["United States"],
                    "purpose": "Managed model inference",
                }
            ],
            "transfer_mechanism": "contractual mechanism pending privacy validation",
            "legal_basis": "contract performance and legitimate interest assessment",
            "safeguards": ["encryption", "no provider training", "retention limit"],
            "residual_risk": "high",
        }
    }


async def test_structured_assessments_are_saved_versioned_and_submitted(
    client: AsyncClient,
) -> None:
    """Cover all definitions plus update, listing, and submit transitions."""
    initiative = await client.post(
        "/api/v1/initiatives",
        json=initiative_payload(),
        headers=OWNER_HEADERS,
    )
    assert initiative.status_code == 201
    initiative_id = initiative.json()["id"]

    created_aia = await client.put(
        f"/api/v1/initiatives/{initiative_id}/assessments/ai-impact-assessment",
        json=impact_payload(),
        headers=OWNER_HEADERS,
    )
    assert created_aia.status_code == 200
    assert created_aia.json()["schema_version"] == "1.0.0"
    assert created_aia.json()["risk_score"] == 40

    created_ripd = await client.put(
        f"/api/v1/initiatives/{initiative_id}/assessments/ripd",
        json=ripd_payload(),
        headers=OWNER_HEADERS,
    )
    assert created_ripd.status_code == 200

    created_international = await client.put(
        f"/api/v1/initiatives/{initiative_id}/assessments/international-processing-assessment",
        json=international_payload(),
        headers=OWNER_HEADERS,
    )
    assert created_international.status_code == 200
    assert created_international.json()["risk_tier"] == "high"

    conflict = await client.put(
        f"/api/v1/initiatives/{initiative_id}/assessments/ai-impact-assessment",
        json=impact_payload(expected_version=999),
        headers=OWNER_HEADERS,
    )
    assert conflict.status_code == 409

    updated = await client.put(
        f"/api/v1/initiatives/{initiative_id}/assessments/ai-impact-assessment",
        json=impact_payload(expected_version=created_aia.json()["version"]),
        headers=OWNER_HEADERS,
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    listed = await client.get(
        f"/api/v1/initiatives/{initiative_id}/assessments",
        headers=OWNER_HEADERS,
    )
    assert listed.status_code == 200
    assert {item["assessment_type"] for item in listed.json()} == {
        "ai-impact-assessment",
        "ripd",
        "international-processing-assessment",
    }

    submitted = await client.post(
        f"/api/v1/assessments/{updated.json()['id']}/submit",
        json={"expected_version": updated.json()["version"]},
        headers=OWNER_HEADERS,
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "under_review"

    immutable = await client.put(
        f"/api/v1/initiatives/{initiative_id}/assessments/ai-impact-assessment",
        json=impact_payload(expected_version=submitted.json()["version"]),
        headers=OWNER_HEADERS,
    )
    assert immutable.status_code == 409


async def test_assessment_applicability_and_owner_fail_closed(client: AsyncClient) -> None:
    """Reject owner violations and assessments unsupported by proposal facts."""
    initiative = await client.post(
        "/api/v1/initiatives",
        json=initiative_payload(personal_data=False),
        headers=OWNER_HEADERS,
    )
    initiative_id = initiative.json()["id"]

    inapplicable = await client.put(
        f"/api/v1/initiatives/{initiative_id}/assessments/ripd",
        json=ripd_payload(),
        headers=OWNER_HEADERS,
    )
    assert inapplicable.status_code == 422

    forbidden = await client.put(
        f"/api/v1/initiatives/{initiative_id}/assessments/ai-impact-assessment",
        json=impact_payload(),
        headers={"X-User-Id": "unrelated-user"},
    )
    assert forbidden.status_code == 403

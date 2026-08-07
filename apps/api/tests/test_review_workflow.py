"""HTTP integration tests for immutable review and resubmission rounds."""

from typing import Any

from ai_governance_api.database import SessionFactory
from ai_governance_api.models import ReviewSubmission
from httpx import AsyncClient
from sqlalchemy import select

OWNER_HEADERS = {"X-User-Id": "review-owner"}
BUSINESS_REVIEWER = {
    "X-User-Id": "business-reviewer",
    "X-User-Areas": "business",
}


def initiative_payload() -> dict[str, Any]:
    """Return a low-risk proposal with one required business gate."""
    return {
        "name": "Assistente editorial interno",
        "description": "Apoia a revisão de conteúdo público sem executar decisões ou ações.",
        "business_area": "Comunicação",
        "intended_users": "Equipe editorial interna",
        "decision_impact": "informational",
        "data_classification": "public",
        "autonomy_level": "a0_information",
        "hosting_model": "saas",
    }


def impact_payload(
    *,
    expected_version: int | None,
    intended_benefits: str,
) -> dict[str, Any]:
    """Return a complete versioned AI impact assessment."""
    return {
        "expected_version": expected_version,
        "answers": {
            "assessment_type": "ai-impact-assessment",
            "affected_groups": ["editorial workers"],
            "intended_benefits": intended_benefits,
            "potential_harms": ["incorrect wording"],
            "human_oversight": "An editor reviews every suggested change before publication.",
            "contestability": "Editors can discard suggestions and report recurring errors.",
            "mitigation_measures": ["human review", "quality samples"],
            "residual_risk": "low",
        },
    }


async def test_change_request_resubmission_preserves_review_history(
    client: AsyncClient,
) -> None:
    """Exercise corrections, assessment reopening, and a fresh approval round."""
    created = await client.post(
        "/api/v1/initiatives",
        json=initiative_payload(),
        headers=OWNER_HEADERS,
    )
    assert created.status_code == 201
    initiative = created.json()
    initiative_id = initiative["id"]

    assessment = await client.put(
        f"/api/v1/initiatives/{initiative_id}/assessments/ai-impact-assessment",
        json=impact_payload(
            expected_version=None,
            intended_benefits="Improve the consistency of internal editorial review.",
        ),
        headers=OWNER_HEADERS,
    )
    submitted_assessment = await client.post(
        f"/api/v1/assessments/{assessment.json()['id']}/submit",
        json={"expected_version": assessment.json()["version"]},
        headers=OWNER_HEADERS,
    )
    assert submitted_assessment.status_code == 200

    submitted = await client.post(
        f"/api/v1/initiatives/{initiative_id}/submit",
        json={"expected_version": initiative["version"]},
        headers=OWNER_HEADERS,
    )
    assert submitted.status_code == 200
    first_round = submitted.json()
    assert first_round["current_review_round"] == 1
    first_gate = next(item for item in first_round["approvals"] if item["required"])

    requested = await client.post(
        f"/api/v1/initiatives/{initiative_id}/approvals/{first_gate['id']}/decision",
        json={
            "decision": "changes_requested",
            "comments": "Detalhar os limites de uso e a supervisão editorial.",
            "evidence_uri": "urn:review:first-round",
            "expected_version": first_gate["version"],
        },
        headers=BUSINESS_REVIEWER,
    )
    assert requested.status_code == 200
    requested_body = requested.json()
    assert requested_body["status"] == "changes_requested"

    reopened = await client.get(
        f"/api/v1/initiatives/{initiative_id}/assessments",
        headers=OWNER_HEADERS,
    )
    reopened_assessment = reopened.json()[0]
    assert reopened_assessment["status"] == "draft"
    assert reopened_assessment["version"] == submitted_assessment.json()["version"] + 1

    blocked = await client.post(
        f"/api/v1/initiatives/{initiative_id}/resubmit",
        json={
            "expected_version": requested_body["version"],
            "revision_summary": "Tentativa anterior à correção da avaliação reaberta.",
        },
        headers=OWNER_HEADERS,
    )
    assert blocked.status_code == 422
    assert "ai-impact-assessment" in blocked.text

    updated_assessment = await client.put(
        f"/api/v1/initiatives/{initiative_id}/assessments/ai-impact-assessment",
        json=impact_payload(
            expected_version=reopened_assessment["version"],
            intended_benefits="Improve consistency within an explicitly limited editorial scope.",
        ),
        headers=OWNER_HEADERS,
    )
    resubmitted_assessment = await client.post(
        f"/api/v1/assessments/{updated_assessment.json()['id']}/submit",
        json={"expected_version": updated_assessment.json()["version"]},
        headers=OWNER_HEADERS,
    )
    assert resubmitted_assessment.status_code == 200

    revised_description = (
        "Apoia a revisão de conteúdo público dentro de um escopo editorial limitado "
        "e com validação humana obrigatória."
    )
    revised = await client.put(
        f"/api/v1/initiatives/{initiative_id}/revision",
        json={
            "expected_version": requested_body["version"],
            "change_reason": "Registrar o escopo e a supervisão solicitados.",
            "description": revised_description,
        },
        headers=OWNER_HEADERS,
    )
    assert revised.status_code == 200
    assert revised.json()["status"] == "changes_requested"
    assert revised.json()["description"] == revised_description

    resubmitted = await client.post(
        f"/api/v1/initiatives/{initiative_id}/resubmit",
        json={
            "expected_version": revised.json()["version"],
            "revision_summary": "Escopo limitado e supervisão humana explicitados.",
        },
        headers=OWNER_HEADERS,
    )
    assert resubmitted.status_code == 200
    second_round = resubmitted.json()
    assert second_round["status"] == "under_review"
    assert second_round["current_review_round"] == 2
    assert len(second_round["approvals"]) == 9
    assert all(item["review_round"] == 2 for item in second_round["approvals"])

    history = await client.get(
        f"/api/v1/initiatives/{initiative_id}/review-history",
        headers=OWNER_HEADERS,
    )
    assert history.status_code == 200
    rounds = history.json()
    assert [item["review_round"] for item in rounds] == [1, 2]
    assert rounds[0]["status"] == "changes_requested"
    assert rounds[1]["revision_summary"].startswith("Escopo limitado")
    assert "initiative_snapshot" not in rounds[0]
    assert "assessment_snapshots" not in rounds[0]

    forbidden_history = await client.get(
        f"/api/v1/initiatives/{initiative_id}/review-history",
        headers={"X-User-Id": "unrelated-user"},
    )
    assert forbidden_history.status_code == 403

    stale_gate = await client.post(
        f"/api/v1/initiatives/{initiative_id}/approvals/{first_gate['id']}/decision",
        json={
            "decision": "approved",
            "comments": "Esta decisão pertence a uma rodada encerrada.",
            "evidence_uri": "urn:review:stale-round",
            "expected_version": first_gate["version"] + 1,
        },
        headers=BUSINESS_REVIEWER,
    )
    assert stale_gate.status_code == 409

    second_gate = next(
        item for item in second_round["approvals"] if item["review_round"] == 2 and item["required"]
    )
    approved = await client.post(
        f"/api/v1/initiatives/{initiative_id}/approvals/{second_gate['id']}/decision",
        json={
            "decision": "approved",
            "comments": "As correções solicitadas foram verificadas na nova rodada.",
            "evidence_uri": "urn:review:second-round",
            "expected_version": second_gate["version"],
        },
        headers=BUSINESS_REVIEWER,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    async with SessionFactory() as session:
        stored_rounds = list(
            await session.scalars(
                select(ReviewSubmission)
                .where(ReviewSubmission.initiative_id == initiative_id)
                .order_by(ReviewSubmission.review_round)
            )
        )
    assert stored_rounds[0].initiative_snapshot["description"] == initiative["description"]
    assert stored_rounds[1].initiative_snapshot["description"] == revised_description
    assert (
        stored_rounds[0].assessment_snapshots[0]["answers"]["intended_benefits"]
        == "Improve the consistency of internal editorial review."
    )
    assert (
        stored_rounds[1].assessment_snapshots[0]["answers"]["intended_benefits"]
        == "Improve consistency within an explicitly limited editorial scope."
    )

    audit = await client.get(
        f"/api/v1/initiatives/{initiative_id}/audit",
        headers=OWNER_HEADERS,
    )
    assert [event["action"] for event in audit.json()] == [
        "initiative.created",
        "initiative.submitted",
        "review.changes_requested",
        "initiative.revision_saved",
        "initiative.resubmitted",
        "approval.decided",
    ]


async def test_revision_recalculates_new_assessment_requirements_fail_closed(
    client: AsyncClient,
) -> None:
    """A material revision must be saved before newly required documents can exist."""
    initiative = (
        await client.post(
            "/api/v1/initiatives",
            json=initiative_payload(),
            headers=OWNER_HEADERS,
        )
    ).json()
    initiative_id = initiative["id"]
    assessment = (
        await client.put(
            f"/api/v1/initiatives/{initiative_id}/assessments/ai-impact-assessment",
            json=impact_payload(
                expected_version=None,
                intended_benefits="Improve editorial review consistency.",
            ),
            headers=OWNER_HEADERS,
        )
    ).json()
    submitted_assessment = (
        await client.post(
            f"/api/v1/assessments/{assessment['id']}/submit",
            json={"expected_version": assessment["version"]},
            headers=OWNER_HEADERS,
        )
    ).json()
    submitted = (
        await client.post(
            f"/api/v1/initiatives/{initiative_id}/submit",
            json={"expected_version": initiative["version"]},
            headers=OWNER_HEADERS,
        )
    ).json()
    gate = next(item for item in submitted["approvals"] if item["required"])
    requested = (
        await client.post(
            f"/api/v1/initiatives/{initiative_id}/approvals/{gate['id']}/decision",
            json={
                "decision": "changes_requested",
                "comments": "Avaliar o novo uso de dados pessoais antes do reenvio.",
                "evidence_uri": "urn:review:data-change",
                "expected_version": gate["version"],
            },
            headers=BUSINESS_REVIEWER,
        )
    ).json()
    reopened_version = submitted_assessment["version"] + 1
    updated = (
        await client.put(
            f"/api/v1/initiatives/{initiative_id}/assessments/ai-impact-assessment",
            json=impact_payload(
                expected_version=reopened_version,
                intended_benefits="Improve review with a documented personal-data scope.",
            ),
            headers=OWNER_HEADERS,
        )
    ).json()
    await client.post(
        f"/api/v1/assessments/{updated['id']}/submit",
        json={"expected_version": updated["version"]},
        headers=OWNER_HEADERS,
    )

    forbidden = await client.put(
        f"/api/v1/initiatives/{initiative_id}/revision",
        json={
            "expected_version": requested["version"],
            "change_reason": "Mudança tentada por usuário sem ownership.",
            "personal_data": True,
        },
        headers={"X-User-Id": "unrelated-user"},
    )
    assert forbidden.status_code == 403

    revised = await client.put(
        f"/api/v1/initiatives/{initiative_id}/revision",
        json={
            "expected_version": requested["version"],
            "change_reason": "Declarar o novo tratamento de dados pessoais.",
            "personal_data": True,
            "data_classification": "confidential",
        },
        headers=OWNER_HEADERS,
    )
    assert revised.status_code == 200
    assert "ripd" in revised.json()["required_documents"]

    blocked = await client.post(
        f"/api/v1/initiatives/{initiative_id}/resubmit",
        json={
            "expected_version": revised.json()["version"],
            "revision_summary": "Tratamento pessoal declarado e avaliação atualizada.",
        },
        headers=OWNER_HEADERS,
    )
    assert blocked.status_code == 422
    assert "ripd" in blocked.text

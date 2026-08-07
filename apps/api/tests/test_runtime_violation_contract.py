"""P1.4 contract tests for durable runtime violation evidence."""

import json
from pathlib import Path

import pytest
from governance_schemas import RuntimeViolationEnvelope


def _fixture() -> dict[str, object]:
    path = (
        Path(__file__).resolve().parents[3]
        / "contracts/runtime-violation/credit-pj-model-scope-v1.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_checked_in_violation_fixture_is_digest_valid() -> None:
    envelope = RuntimeViolationEnvelope.model_validate(_fixture())

    assert envelope.event.code == "selected_model_group_not_authorized"
    assert envelope.event.category.value == "model_scope"
    assert envelope.event_digest == envelope.event.digest()


def test_violation_digest_rejects_tampering() -> None:
    payload = _fixture()
    event = payload["event"]
    assert isinstance(event, dict)
    event["selected_model_group"] = "reasoning-strong"

    with pytest.raises(ValueError):
        RuntimeViolationEnvelope.model_validate(payload)


def test_violation_fixture_contains_no_content_or_credentials() -> None:
    serialized = json.dumps(_fixture(), ensure_ascii=False).lower()

    for forbidden in (
        "prompt",
        "model_output",
        "document_content",
        "x-api-key",
        "authorization_header",
        "credential",
    ):
        assert forbidden not in serialized

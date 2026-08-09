"""Pure tests for the P1.6d live cross-repository verification harness."""

import json
from pathlib import Path

import pytest

from scripts.verify_p1_6_cross_repo_e2e import (
    VerificationError,
    load_agent_id,
    parse_router_envelope,
    routing_payload,
)


def _router_envelope(*, agent_version: object = 7) -> bytes:
    return json.dumps(
        {
            "request": {
                "workflow_id": "wf-1",
                "task_id": "task-1",
            },
            "authorization": {
                "claims": {
                    "authorization_id": "auth-1",
                    "subject": {
                        "agent_version": agent_version,
                    },
                }
            },
        }
    ).encode()


def test_parse_router_envelope_extracts_only_required_signed_identifiers() -> None:
    result = parse_router_envelope(_router_envelope())

    assert result == {
        "authorization_id": "auth-1",
        "agent_version": 7,
        "workflow_id": "wf-1",
        "task_id": "task-1",
    }


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"{}",
        _router_envelope(agent_version=0),
        _router_envelope(agent_version=True),
    ],
)
def test_parse_router_envelope_fails_closed_for_invalid_barrier_input(body: bytes) -> None:
    with pytest.raises(VerificationError):
        parse_router_envelope(body)


def test_routing_payload_is_deterministic_except_for_task_identifier() -> None:
    left = routing_payload("A")
    right = routing_payload("B")

    assert left["task_id"] == "A"
    assert right["task_id"] == "B"
    assert {key: value for key, value in left.items() if key != "task_id"} == {
        key: value for key, value in right.items() if key != "task_id"
    }


def test_load_agent_id_prefers_explicit_value(tmp_path: Path) -> None:
    missing_manifest = tmp_path / "missing.json"

    assert load_agent_id("agent-explicit", missing_manifest) == "agent-explicit"


def test_load_agent_id_reads_canonical_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"agent_id": "agent-from-seed"}))

    assert load_agent_id(None, manifest) == "agent-from-seed"


def test_load_agent_id_rejects_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(VerificationError):
        load_agent_id(None, tmp_path / "missing.json")

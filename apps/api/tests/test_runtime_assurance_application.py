from datetime import UTC, datetime, timedelta

import pytest
from ai_governance_api.application.runtime_assurance import (
    RuntimeAssuranceScope,
    RuntimeAssuranceService,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.runtime_assurance import (
    RuntimeAssuranceEvaluation,
    RuntimeAssurancePolicy,
    RuntimeAssuranceSample,
)
from ai_governance_api.errors import ApplicationError
from governance_schemas import RiskTier

NOW = datetime(2026, 8, 9, 18, 0, tzinfo=UTC)


class Repository:
    def __init__(self) -> None:
        self.scope = RuntimeAssuranceScope(
            agent_id="agent-1",
            ai_system_id="system-1",
            initiative_id="initiative-1",
            agent_owner_id="agent-owner",
            ai_system_owner_id="system-owner",
        )
        self.policy: RuntimeAssurancePolicy | None = None
        self.samples: list[RuntimeAssuranceSample] = []
        self.evaluations: list[RuntimeAssuranceEvaluation] = []

    async def get_scope(self, agent_id: str, *, for_update: bool = False):
        del for_update
        return self.scope if agent_id == self.scope.agent_id else None

    async def get_policy(self, agent_id: str, *, for_update: bool = False):
        del for_update
        return self.policy if agent_id == self.scope.agent_id else None

    async def save_policy(self, policy: RuntimeAssurancePolicy):
        self.policy = policy
        return policy

    async def list_terminal_samples(self, agent_id: str, *, since, until, limit: int):
        del agent_id, since, until
        return self.samples[-limit:]

    async def save_evaluation(self, evaluation: RuntimeAssuranceEvaluation):
        self.evaluations.append(evaluation)
        return evaluation

    async def list_evaluations(self, agent_id: str, *, limit: int):
        del agent_id
        return self.evaluations[-limit:]


class Audit:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def append(self, **kwargs):
        self.events.append(kwargs)


class Transaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def service():
    repo = Repository()
    audit = Audit()
    transaction = Transaction()
    instance = RuntimeAssuranceService(
        repo,
        audit,
        transaction,
        clock=lambda: NOW,
    )
    return instance, repo, audit, transaction


def policy_kwargs() -> dict[str, object]:
    return {
        "agent_id": "agent-1",
        "enabled": True,
        "lookback_seconds": 300,
        "evaluation_sample_size": 10,
        "minimum_samples": 2,
        "max_failure_rate": 0.5,
        "max_p95_duration_ms": 500.0,
        "max_consecutive_failures": 2,
        "breach_severity": RiskTier.HIGH,
    }


async def test_create_then_versioned_update_is_audited() -> None:
    instance, repo, audit, transaction = service()
    owner = Principal(user_id="agent-owner")
    created = await instance.put_policy(**policy_kwargs(), expected_version=None, principal=owner)
    assert created.version == 1
    updated = await instance.put_policy(**policy_kwargs(), expected_version=1, principal=owner)
    assert updated.version == 2
    assert repo.policy == updated
    assert [event["action"] for event in audit.events] == [
        "runtime_assurance.policy_created",
        "runtime_assurance.policy_updated",
    ]
    assert transaction.commits == 2


async def test_stale_policy_update_is_rejected() -> None:
    instance, _, _, _ = service()
    owner = Principal(user_id="agent-owner")
    await instance.put_policy(**policy_kwargs(), expected_version=None, principal=owner)
    with pytest.raises(ApplicationError, match="version conflict"):
        await instance.put_policy(**policy_kwargs(), expected_version=99, principal=owner)


async def test_non_owner_cannot_manage_assurance() -> None:
    instance, _, _, _ = service()
    with pytest.raises(ApplicationError, match="Only the system owner"):
        await instance.put_policy(
            **policy_kwargs(),
            expected_version=None,
            principal=Principal(user_id="other-user"),
        )


async def test_disabled_policy_cannot_emit_evaluation_evidence() -> None:
    instance, repo, _, _ = service()
    owner = Principal(user_id="agent-owner")
    disabled = policy_kwargs()
    disabled["enabled"] = False
    await instance.put_policy(**disabled, expected_version=None, principal=owner)
    with pytest.raises(ApplicationError, match="disabled"):
        await instance.evaluate(agent_id="agent-1", principal=owner)
    assert repo.evaluations == []


async def test_evaluation_is_persisted_and_minimally_audited() -> None:
    instance, repo, audit, transaction = service()
    owner = Principal(user_id="system-owner")
    await instance.put_policy(**policy_kwargs(), expected_version=None, principal=owner)
    repo.samples = [
        RuntimeAssuranceSample(
            event_id="event-1",
            observed_at=NOW - timedelta(seconds=3),
            event_outcome="failure",
            duration_ms=100.0,
        ),
        RuntimeAssuranceSample(
            event_id="event-2",
            observed_at=NOW - timedelta(seconds=2),
            event_outcome="failure",
            duration_ms=200.0,
        ),
    ]
    evaluation = await instance.evaluate(agent_id="agent-1", principal=owner)
    assert len(repo.evaluations) == 1
    assert evaluation.source_event_ids == ("event-1", "event-2")
    event = audit.events[-1]
    assert event["action"] == "runtime_assurance.evaluated"
    audit_payload = event["payload"]
    assert isinstance(audit_payload, dict)
    assert "source_event_ids" not in audit_payload
    assert "failure_rate" not in audit_payload
    assert audit_payload["evidence_digest"] == evaluation.evidence_digest
    assert transaction.commits == 2

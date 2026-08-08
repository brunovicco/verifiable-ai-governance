"""Unit tests for monotonic emergency runtime-control transitions."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ai_governance_api.adapters.runtime_control_redis import InMemoryRuntimeControlStore
from ai_governance_api.application.runtime_control import RuntimeControlGate, RuntimeControlService
from ai_governance_api.domain.identity import Principal
from ai_governance_api.domain.runtime_control import (
    RuntimeControlAgentContext,
    RuntimeControlDurableState,
    RuntimeControlSnapshot,
    RuntimeControlState,
    RuntimeControlTransitionRecord,
    RuntimeControlTransitionStatus,
    RuntimeControlUnavailable,
)
from ai_governance_api.errors import ApplicationError, ErrorKind

NOW = datetime(2026, 8, 8, 21, 0, tzinfo=UTC)


class FakeRepository:
    def __init__(self) -> None:
        self.context = RuntimeControlAgentContext(
            agent_id="agent-1",
            ai_system_id="system-1",
            ai_system_owner_id="system-owner",
            agent_owner_id="agent-owner",
            kill_switch_enabled=True,
            kill_switch_engaged=False,
            agent_version=7,
        )
        self.transitions: dict[str, RuntimeControlTransitionRecord] = {}

    async def get_agent_for_update(self, agent_id, *, incident_id):
        del incident_id
        return (self.context, None) if agent_id == self.context.agent_id else None

    async def get_latest_transition_for_update(self, agent_id):
        values = [value for value in self.transitions.values() if value.agent_id == agent_id]
        return max(values, key=lambda value: value.control_epoch) if values else None

    async def get_transition(self, transition_id):
        return self.transitions.get(transition_id)

    async def get_transition_for_update(self, transition_id):
        return self.transitions.get(transition_id)

    async def save_transition(self, transition):
        self.transitions[transition.id] = transition
        return transition

    async def apply_agent_state(self, context, *, engaged, actor_id, changed_at):
        del actor_id, changed_at
        self.context = replace(
            context,
            kill_switch_engaged=engaged,
            agent_version=context.agent_version + 1,
        )
        return self.context

    async def list_pending(self, *, limit):
        return [
            transition
            for transition in sorted(
                self.transitions.values(), key=lambda item: item.control_epoch
            )
            if transition.status is RuntimeControlTransitionStatus.PENDING
        ][:limit]


class FakeAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def append(self, *, actor_id, action, transition):
        del actor_id, transition
        self.actions.append(action)


class FakeTransaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class ToggleProjection(InMemoryRuntimeControlStore):
    def __init__(self) -> None:
        super().__init__()
        self.fail_project = False

    async def project(self, snapshot):
        if self.fail_project:
            raise RuntimeControlUnavailable("synthetic outage")
        await super().project(snapshot)


def _service(repository, projection, audit, transaction):
    ids = iter(["transition-1", "transition-2"])
    return RuntimeControlService(
        repository,
        projection,
        audit,
        transaction,
        clock=lambda: NOW,
        id_factory=lambda: next(ids),
    )


def test_activate_then_deactivate_keeps_old_agent_version_revoked() -> None:
    async def scenario() -> None:
        repository = FakeRepository()
        projection = ToggleProjection()
        audit = FakeAudit()
        transaction = FakeTransaction()
        service = _service(repository, projection, audit, transaction)
        principal = Principal(user_id="agent-owner")

        activated = await service.activate(
            agent_id="agent-1",
            expected_version=7,
            reason="Emergency containment",
            principal=principal,
        )
        assert activated.kill_switch_engaged is True
        assert activated.agent_version == 8
        assert activated.transition.control_epoch == 1
        assert activated.transition.revoked_through_agent_version == 7

        restored = await service.deactivate(
            agent_id="agent-1",
            expected_version=8,
            reason="Remediation verified",
            principal=principal,
        )
        assert restored.kill_switch_engaged is False
        assert restored.agent_version == 9
        assert restored.transition.control_epoch == 2
        assert restored.transition.revoked_through_agent_version == 8
        snapshot = await projection.read("agent-1")
        assert snapshot is not None
        assert snapshot.state is RuntimeControlState.INACTIVE
        assert snapshot.revoked_through_agent_version == 8
        assert audit.actions == [
            "runtime_control.activation_requested",
            "runtime_control.activated",
            "runtime_control.deactivation_requested",
            "runtime_control.deactivated",
        ]

    asyncio.run(scenario())


def test_projection_failure_leaves_pending_transition_for_reconciliation() -> None:
    async def scenario() -> None:
        repository = FakeRepository()
        projection = ToggleProjection()
        projection.fail_project = True
        audit = FakeAudit()
        transaction = FakeTransaction()
        service = _service(repository, projection, audit, transaction)

        with pytest.raises(ApplicationError) as raised:
            await service.activate(
                agent_id="agent-1",
                expected_version=7,
                reason="Emergency containment",
                principal=Principal(user_id="agent-owner"),
            )
        assert raised.value.kind is ErrorKind.DEPENDENCY_UNAVAILABLE
        pending = repository.transitions["transition-1"]
        assert pending.status is RuntimeControlTransitionStatus.PENDING
        assert repository.context.kill_switch_engaged is False

        projection.fail_project = False
        reconciled = await service.reconcile_pending(
            principal=Principal(user_id="admin", is_admin=True),
            limit=10,
        )
        assert len(reconciled) == 1
        assert reconciled[0].kill_switch_engaged is True
        assert (
            repository.transitions["transition-1"].status
            is RuntimeControlTransitionStatus.APPLIED
        )
        assert "runtime_control.projection_reconciled" in audit.actions

    asyncio.run(scenario())


def test_gate_repairs_missing_projection_but_rejects_ambiguous_divergence() -> None:
    class Reader:
        async def get_durable_state(self, agent_id):
            return RuntimeControlDurableState(
                snapshot=RuntimeControlSnapshot(
                    agent_id=agent_id,
                    control_epoch=3,
                    state=RuntimeControlState.INACTIVE,
                    revoked_through_agent_version=12,
                    transition_id="transition-3",
                ),
                pending_transition_id=None,
                durable_consistent=True,
            )

    async def scenario() -> None:
        projection = InMemoryRuntimeControlStore()
        gate = RuntimeControlGate(Reader(), projection)
        assert await gate.state_for("agent-1") is RuntimeControlState.INACTIVE
        assert (await projection.read("agent-1")) is not None

        await projection.project(
            RuntimeControlSnapshot(
                agent_id="agent-2",
                control_epoch=3,
                state=RuntimeControlState.ACTIVE,
                revoked_through_agent_version=12,
                transition_id="transition-3",
            )
        )
        with pytest.raises(RuntimeControlUnavailable):
            await gate.state_for("agent-2")

    asyncio.run(scenario())

def test_gate_rejects_pending_transition_without_reading_as_inactive() -> None:
    class Reader:
        async def get_durable_state(self, agent_id):
            return RuntimeControlDurableState(
                snapshot=RuntimeControlSnapshot(
                    agent_id=agent_id,
                    control_epoch=4,
                    state=RuntimeControlState.INACTIVE,
                    revoked_through_agent_version=13,
                    transition_id="transition-4",
                ),
                pending_transition_id="transition-4",
                durable_consistent=True,
            )

    async def scenario() -> None:
        gate = RuntimeControlGate(Reader(), InMemoryRuntimeControlStore())
        with pytest.raises(RuntimeControlUnavailable):
            await gate.state_for("agent-1")

    asyncio.run(scenario())


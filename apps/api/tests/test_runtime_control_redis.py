"""Contract tests for monotonic process-local runtime-control projection semantics."""

import asyncio

import pytest
from ai_governance_api.adapters.runtime_control_redis import InMemoryRuntimeControlStore
from ai_governance_api.domain.runtime_control import (
    RuntimeControlSnapshot,
    RuntimeControlState,
    RuntimeControlUnavailable,
)


def _snapshot(epoch: int, state: RuntimeControlState, transition: str) -> RuntimeControlSnapshot:
    return RuntimeControlSnapshot(
        agent_id="agent-1",
        control_epoch=epoch,
        state=state,
        revoked_through_agent_version=epoch + 10,
        transition_id=transition,
    )


def test_projection_is_monotonic_idempotent_and_rejects_same_epoch_conflicts() -> None:
    async def scenario() -> None:
        store = InMemoryRuntimeControlStore()
        first = _snapshot(1, RuntimeControlState.ACTIVE, "transition-1")
        await store.project(first)
        await store.project(first)
        await store.project(_snapshot(2, RuntimeControlState.INACTIVE, "transition-2"))

        with pytest.raises(RuntimeControlUnavailable):
            await store.project(first)
        with pytest.raises(RuntimeControlUnavailable):
            await store.project(_snapshot(2, RuntimeControlState.ACTIVE, "transition-other"))

        observed = await store.read("agent-1")
        assert observed is not None
        assert observed.control_epoch == 2
        assert observed.state is RuntimeControlState.INACTIVE

    asyncio.run(scenario())

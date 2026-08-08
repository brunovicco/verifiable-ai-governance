"""Monotonic Redis and in-memory projections for emergency runtime control."""

import asyncio
import json
from typing import Any

from redis.asyncio import Redis

from ai_governance_api.domain.runtime_control import (
    RuntimeControlSnapshot,
    RuntimeControlState,
    RuntimeControlUnavailable,
)

_MAX_SNAPSHOT_BYTES = 4096

_CAS_SCRIPT = """
local current = redis.call('GET', KEYS[1])
local incoming_epoch = tonumber(ARGV[1])
local incoming_payload = ARGV[2]
if current then
  local decoded = cjson.decode(current)
  local current_epoch = tonumber(decoded['control_epoch'])
  if current_epoch > incoming_epoch then
    return -1
  end
  if current_epoch == incoming_epoch then
    if current == incoming_payload then
      return 0
    end
    return -2
  end
end
redis.call('SET', KEYS[1], incoming_payload)
return 1
"""


class InMemoryRuntimeControlStore:
    """Process-local monotonic projection for local development and tests."""

    def __init__(self) -> None:
        """Create an empty store protected by one async lock."""
        self._snapshots: dict[str, RuntimeControlSnapshot] = {}
        self._lock = asyncio.Lock()

    async def ping(self) -> None:
        """The process-local store is always reachable."""
        return None

    async def read(self, agent_id: str) -> RuntimeControlSnapshot | None:
        """Return the current snapshot for one agent."""
        async with self._lock:
            return self._snapshots.get(agent_id)

    async def project(self, snapshot: RuntimeControlSnapshot) -> None:
        """Apply only a newer epoch or an identical idempotent write."""
        async with self._lock:
            current = self._snapshots.get(snapshot.agent_id)
            if current is None or snapshot.control_epoch > current.control_epoch:
                self._snapshots[snapshot.agent_id] = snapshot
                return
            if snapshot == current:
                return
            if snapshot.control_epoch < current.control_epoch:
                raise RuntimeControlUnavailable("Runtime-control projection rejected a stale epoch")
            raise RuntimeControlUnavailable(
                "Runtime-control projection rejected conflicting data for the same epoch"
            )

    async def close(self) -> None:
        """No process-external resources are owned."""
        return None


class UnavailableRuntimeControlStore:
    """Fail-closed placeholder used when distributed runtime control is not configured."""

    async def ping(self) -> None:
        """Refuse to claim readiness."""
        raise RuntimeControlUnavailable("Distributed runtime control is not configured")

    async def read(self, agent_id: str) -> RuntimeControlSnapshot | None:
        """Refuse reads rather than assuming an inactive state."""
        del agent_id
        raise RuntimeControlUnavailable("Distributed runtime control is not configured")

    async def project(self, snapshot: RuntimeControlSnapshot) -> None:
        """Refuse writes rather than acknowledging an unsafe state."""
        del snapshot
        raise RuntimeControlUnavailable("Distributed runtime control is not configured")

    async def close(self) -> None:
        """No resources are owned."""
        return None


class RedisRuntimeControlStore:
    """Cross-replica runtime-control projection using atomic epoch CAS."""

    def __init__(self, client: Any, *, key_prefix: str) -> None:
        """Wrap an async Redis client with an explicit namespace."""
        if not key_prefix.strip():
            raise ValueError("Runtime-control key prefix must not be empty")
        self._client = client
        self._key_prefix = key_prefix

    async def ping(self) -> None:
        """Require Redis to respond before a transition is durably requested."""
        try:
            await self._client.ping()
        except Exception as exc:
            raise RuntimeControlUnavailable("Runtime-control Redis is unavailable") from exc

    async def read(self, agent_id: str) -> RuntimeControlSnapshot | None:
        """Read and strictly validate one bounded JSON snapshot."""
        try:
            raw = await self._client.get(self._key(agent_id))
        except Exception as exc:
            raise RuntimeControlUnavailable("Runtime-control Redis is unavailable") from exc
        if raw is None:
            return None
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise RuntimeControlUnavailable("Runtime-control snapshot is not UTF-8") from exc
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > _MAX_SNAPSHOT_BYTES:
            raise RuntimeControlUnavailable("Runtime-control snapshot is invalid")
        return _parse_snapshot(raw, expected_agent_id=agent_id)

    async def project(self, snapshot: RuntimeControlSnapshot) -> None:
        """Atomically reject stale epochs and conflicting same-epoch writes."""
        payload = _snapshot_json(snapshot)
        try:
            result = await self._client.eval(
                _CAS_SCRIPT,
                1,
                self._key(snapshot.agent_id),
                str(snapshot.control_epoch),
                payload,
            )
        except Exception as exc:
            raise RuntimeControlUnavailable("Runtime-control Redis is unavailable") from exc
        if result in {0, 1}:
            return
        if result == -1:
            raise RuntimeControlUnavailable("Runtime-control projection rejected a stale epoch")
        raise RuntimeControlUnavailable(
            "Runtime-control projection rejected conflicting data for the same epoch"
        )

    async def close(self) -> None:
        """Close the owned Redis client."""
        close = getattr(self._client, "aclose", None)
        if close is not None:
            await close()

    def _key(self, agent_id: str) -> str:
        if not agent_id:
            raise RuntimeControlUnavailable("Runtime-control agent identifier is empty")
        return f"{self._key_prefix}{agent_id}"


def build_redis_runtime_control_store(
    *,
    redis_url: str,
    key_prefix: str,
    timeout_seconds: float,
) -> RedisRuntimeControlStore:
    """Build the shared Redis projection with bounded connect and command timeouts."""
    client = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=timeout_seconds,
        socket_timeout=timeout_seconds,
    )
    return RedisRuntimeControlStore(client, key_prefix=key_prefix)


def _snapshot_json(snapshot: RuntimeControlSnapshot) -> str:
    payload = json.dumps(
        {
            "agent_id": snapshot.agent_id,
            "control_epoch": snapshot.control_epoch,
            "revoked_through_agent_version": snapshot.revoked_through_agent_version,
            "schema_version": snapshot.schema_version,
            "state": snapshot.state.value,
            "transition_id": snapshot.transition_id,
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(payload.encode("utf-8")) > _MAX_SNAPSHOT_BYTES:
        raise RuntimeControlUnavailable("Runtime-control snapshot exceeds its size limit")
    return payload


def _parse_snapshot(raw: str, *, expected_agent_id: str) -> RuntimeControlSnapshot:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeControlUnavailable("Runtime-control snapshot is invalid JSON") from exc
    expected_fields = {
        "agent_id",
        "control_epoch",
        "revoked_through_agent_version",
        "schema_version",
        "state",
        "transition_id",
    }
    if not isinstance(document, dict) or set(document) != expected_fields:
        raise RuntimeControlUnavailable("Runtime-control snapshot contains unsupported fields")
    agent_id = document["agent_id"]
    epoch = document["control_epoch"]
    revoked = document["revoked_through_agent_version"]
    transition_id = document["transition_id"]
    if agent_id != expected_agent_id:
        raise RuntimeControlUnavailable("Runtime-control snapshot agent binding is invalid")
    if document["schema_version"] != "1.0":
        raise RuntimeControlUnavailable("Runtime-control snapshot schema is unsupported")
    if (
        not isinstance(epoch, int)
        or isinstance(epoch, bool)
        or epoch < 0
        or not isinstance(revoked, int)
        or isinstance(revoked, bool)
        or revoked < 0
    ):
        raise RuntimeControlUnavailable("Runtime-control snapshot counters are invalid")
    if transition_id is not None and not isinstance(transition_id, str):
        raise RuntimeControlUnavailable("Runtime-control transition identifier is invalid")
    try:
        state = RuntimeControlState(document["state"])
    except (TypeError, ValueError) as exc:
        raise RuntimeControlUnavailable("Runtime-control state is invalid") from exc
    return RuntimeControlSnapshot(
        agent_id=agent_id,
        control_epoch=epoch,
        state=state,
        revoked_through_agent_version=revoked,
        transition_id=transition_id,
    )

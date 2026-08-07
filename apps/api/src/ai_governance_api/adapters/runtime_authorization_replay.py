"""Thread-safe bounded replay protection for single-process consumers."""

from datetime import datetime
from threading import Lock
from uuid import UUID

from ai_governance_api.domain.runtime_authorization_security import (
    RuntimeAuthorizationReplayStoreError,
)


class InMemoryRuntimeAuthorizationReplayGuard:
    """Consume authorization IDs exactly once within their validity window."""

    def __init__(self, *, max_entries: int = 10_000) -> None:
        """Create a bounded process-local replay cache."""
        if max_entries < 1:
            raise ValueError("Replay cache max_entries must be positive")
        self._max_entries = max_entries
        self._entries: dict[UUID, datetime] = {}
        self._lock = Lock()

    def consume(
        self,
        authorization_id: UUID,
        *,
        expires_at: datetime,
        now: datetime,
    ) -> bool:
        """Atomically mark one authorization ID as consumed.

        Return False when the same still-live authorization was already consumed.
        Fail closed when bounded capacity cannot be recovered by pruning expired IDs.
        """
        _require_aware(now)
        _require_aware(expires_at)
        with self._lock:
            self._prune(now)
            existing = self._entries.get(authorization_id)
            if existing is not None and existing > now:
                return False
            if len(self._entries) >= self._max_entries:
                raise RuntimeAuthorizationReplayStoreError(
                    "replay_store_full",
                    "Runtime authorization replay store is at capacity",
                )
            self._entries[authorization_id] = expires_at
            return True

    def _prune(self, now: datetime) -> None:
        """Drop entries whose authorization lifetime has ended."""
        expired = [
            authorization_id
            for authorization_id, expires_at in self._entries.items()
            if expires_at <= now
        ]
        for authorization_id in expired:
            del self._entries[authorization_id]


def _require_aware(value: datetime) -> None:
    """Reject naive replay timestamps."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Replay timestamps must be timezone-aware")

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_governance_api.config import get_settings
from ai_governance_api.models import AuditEvent


async def append_audit_event(
    session: AsyncSession,
    *,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    entity_version: int,
    payload: dict[str, Any],
) -> AuditEvent:
    previous = await session.scalar(
        select(AuditEvent).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(1)
    )
    previous_hash = previous.event_hash if previous else None
    canonical = json.dumps(
        {
            "actor_id": actor_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_version": entity_version,
            "payload": payload,
            "previous_hash": previous_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    event_hash = hashlib.sha256(
        f"{get_settings().audit_hash_salt}:{canonical}".encode()
    ).hexdigest()
    event = AuditEvent(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_version=entity_version,
        payload=payload,
        previous_hash=previous_hash,
        event_hash=event_hash,
    )
    session.add(event)
    return event

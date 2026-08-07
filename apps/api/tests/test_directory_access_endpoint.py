from ai_governance_api.auth import get_principal
from ai_governance_api.config import Settings, get_settings
from ai_governance_api.database import SessionFactory
from ai_governance_api.domain.directory_access import DirectoryAccessTarget
from ai_governance_api.domain.directory_authorization_cache import (
    DirectoryAuthorizationCacheKey,
)
from ai_governance_api.domain.identity import (
    DirectoryAccountType,
    DirectoryIdentity,
    Principal,
)
from ai_governance_api.main import app
from ai_governance_api.models import (
    AuditEvent,
    DirectoryAccessRestrictionEntry,
    DirectoryAuthorizationCacheEntry,
)
from httpx import AsyncClient
from sqlalchemy import select

TENANT_ID = "11111111-1111-4111-8111-111111111111"
OBJECT_ID = "22222222-2222-4222-8222-222222222222"


def target_principal() -> Principal:
    """Return the corporate identity targeted by the incident response."""
    return Principal(
        user_id=f"{TENANT_ID}:{OBJECT_ID}",
        directory_identity=DirectoryIdentity(
            tenant_id=TENANT_ID,
            object_id=OBJECT_ID,
            account_type=DirectoryAccountType.MEMBER,
        ),
    )


async def test_emergency_block_denies_all_routes_until_audited_restore(
    client: AsyncClient,
) -> None:
    actor: dict[str, Principal] = {"current": Principal(user_id="incident-admin", is_admin=True)}
    app.dependency_overrides[get_principal] = lambda: actor["current"]
    app.dependency_overrides[get_settings] = lambda: Settings(
        oidc_enabled=True,
        oidc_identity_mode="entra",
        oidc_allowed_tenant_ids=TENANT_ID,
        oidc_issuer=f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
        oidc_jwks_url=(f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"),
    )
    try:
        blocked = await client.post(
            "/api/v1/auth/directory-access/block",
            json={
                "tenant_id": TENANT_ID,
                "object_id": OBJECT_ID,
                "reason": "account_compromised",
                "reference": "INC-2026-184",
            },
        )
        actor["current"] = target_principal()
        denied = await client.get("/api/v1/initiatives")
        actor["current"] = Principal(user_id="incident-admin", is_admin=True)
        restored = await client.post(
            "/api/v1/auth/directory-access/restore",
            json={
                "tenant_id": TENANT_ID,
                "object_id": OBJECT_ID,
                "reason": "remediation_completed",
                "reference": "INC-2026-184",
            },
        )
        actor["current"] = target_principal()
        allowed = await client.get("/api/v1/initiatives")
    finally:
        app.dependency_overrides.pop(get_principal, None)
        app.dependency_overrides.pop(get_settings, None)

    assert blocked.status_code == 200
    assert blocked.json()["blocked"] is True
    assert denied.status_code == 403
    assert denied.json() == {"detail": "Directory identity access is suspended"}
    assert restored.status_code == 200
    assert restored.json()["blocked"] is False
    assert allowed.status_code == 200

    target = DirectoryAccessTarget(TENANT_ID, OBJECT_ID)
    cache_key = DirectoryAuthorizationCacheKey(TENANT_ID, OBJECT_ID)
    async with SessionFactory() as session:
        restriction = await session.get(DirectoryAccessRestrictionEntry, target.entry_id)
        cache = await session.get(DirectoryAuthorizationCacheEntry, cache_key.entry_id)
        events = list(
            await session.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == "directory_access_restriction")
                .order_by(AuditEvent.occurred_at)
            )
        )

    assert restriction is not None
    assert not restriction.blocked
    assert restriction.version == 2
    assert cache is not None
    assert cache.invalidated_at is not None
    assert [event.action for event in events] == [
        "directory_access.blocked",
        "directory_access.restored",
    ]
    assert all(event.payload["target_digest"] == target.target_digest for event in events)
    assert all(TENANT_ID not in str(event.payload) for event in events)
    assert all(OBJECT_ID not in str(event.payload) for event in events)


async def test_non_admin_cannot_change_directory_access(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/directory-access/block",
        headers={"X-User-Id": "ordinary-user"},
        json={
            "tenant_id": TENANT_ID,
            "object_id": OBJECT_ID,
            "reason": "manual_emergency",
        },
    )

    assert response.status_code == 403

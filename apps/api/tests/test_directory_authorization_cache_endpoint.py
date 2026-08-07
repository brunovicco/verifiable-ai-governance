from ai_governance_api.auth import get_principal
from ai_governance_api.config import Settings, get_settings
from ai_governance_api.database import SessionFactory
from ai_governance_api.domain.directory_authorization_cache import (
    DirectoryAuthorizationCacheKey,
)
from ai_governance_api.domain.identity import Principal
from ai_governance_api.main import app
from ai_governance_api.models import AuditEvent, DirectoryAuthorizationCacheEntry
from httpx import AsyncClient
from sqlalchemy import select

TENANT_ID = "11111111-1111-4111-8111-111111111111"
OBJECT_ID = "22222222-2222-4222-8222-222222222222"


async def test_non_admin_cannot_invalidate_directory_authorization(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/directory-authorization-cache/invalidate",
        headers={"X-User-Id": "ordinary-user"},
        json={
            "tenant_id": TENANT_ID,
            "object_id": OBJECT_ID,
            "reason": "manual_revalidation",
        },
    )

    assert response.status_code == 403


async def test_admin_invalidation_is_shared_and_audited_without_raw_target(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id="platform-administrator",
        is_admin=True,
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        oidc_enabled=True,
        oidc_identity_mode="entra",
        oidc_allowed_tenant_ids=TENANT_ID,
        oidc_issuer=f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
        oidc_jwks_url=(f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"),
    )
    try:
        response = await client.post(
            "/api/v1/auth/directory-authorization-cache/invalidate",
            json={
                "tenant_id": TENANT_ID,
                "object_id": OBJECT_ID,
                "reason": "access_removed",
                "reference": "IAM-2026-184",
            },
        )
    finally:
        app.dependency_overrides.pop(get_principal, None)
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200
    key = DirectoryAuthorizationCacheKey(TENANT_ID, OBJECT_ID)
    assert response.json()["cache_entry_id"] == key.entry_id

    async with SessionFactory() as session:
        entry = await session.get(DirectoryAuthorizationCacheEntry, key.entry_id)
        event = await session.scalar(
            select(AuditEvent).where(AuditEvent.entity_type == "directory_authorization_cache")
        )

    assert entry is not None
    assert entry.invalidated_at is not None
    assert entry.resolved_at is None
    assert entry.approval_areas == []
    assert event is not None
    assert event.payload["reason"] == "access_removed"
    assert event.payload["reference"] == "IAM-2026-184"
    assert event.payload["target_digest"] == key.target_digest
    assert TENANT_ID not in str(event.payload)
    assert OBJECT_ID not in str(event.payload)

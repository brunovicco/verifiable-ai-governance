from datetime import UTC, datetime

import pytest
from ai_governance_api.domain.directory_access import (
    DirectoryAccessError,
    DirectoryAccessState,
    DirectoryAccessTarget,
)

TENANT_ID = "11111111-1111-4111-8111-111111111111"
OBJECT_ID = "22222222-2222-4222-8222-222222222222"
NOW = datetime(2026, 8, 1, 12, tzinfo=UTC)


def test_target_is_canonical_stable_and_content_minimized() -> None:
    target = DirectoryAccessTarget(TENANT_ID.upper(), OBJECT_ID.upper())

    assert target.tenant_id == TENANT_ID
    assert target.object_id == OBJECT_ID
    assert DirectoryAccessTarget(TENANT_ID, OBJECT_ID).entry_id == target.entry_id
    assert TENANT_ID not in target.target_digest
    assert OBJECT_ID not in target.target_digest


@pytest.mark.parametrize("value", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"])
def test_target_rejects_invalid_or_nil_uuid(value: str) -> None:
    with pytest.raises(DirectoryAccessError):
        DirectoryAccessTarget(value, OBJECT_ID)


def test_state_requires_aware_timestamp_and_positive_version() -> None:
    target = DirectoryAccessTarget(TENANT_ID, OBJECT_ID)

    with pytest.raises(DirectoryAccessError, match="timezone-aware"):
        DirectoryAccessState(
            target=target,
            blocked=True,
            changed_at=datetime(2026, 8, 1, 12),
            version=1,
        )

    with pytest.raises(DirectoryAccessError, match="positive"):
        DirectoryAccessState(
            target=target,
            blocked=True,
            changed_at=NOW,
            version=0,
        )

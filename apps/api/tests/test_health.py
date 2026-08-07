from unittest.mock import AsyncMock

import pytest
from ai_governance_api.adapters.runtime_readiness import (
    CheckState,
    RuntimeReadinessReport,
)
from ai_governance_api.routers import health
from httpx import AsyncClient


async def test_legacy_health_remains_backward_compatible(
    client: AsyncClient,
) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_liveness_does_not_run_dependency_checks(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness_check = AsyncMock(side_effect=AssertionError("must not be called"))
    monkeypatch.setattr(health, "check_runtime_readiness", readiness_check)

    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    readiness_check.assert_not_awaited()


async def test_readiness_accepts_current_database_schema(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness_check = AsyncMock(
        return_value=RuntimeReadinessReport(
            database=CheckState.OK,
            schema=CheckState.OK,
        )
    )
    monkeypatch.setattr(health, "check_runtime_readiness", readiness_check)

    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {
            "database": "ok",
            "schema": "ok",
        },
    }
    readiness_check.assert_awaited_once_with()


async def test_readiness_fails_closed_for_schema_mismatch(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness_check = AsyncMock(
        return_value=RuntimeReadinessReport(
            database=CheckState.OK,
            schema=CheckState.MISMATCH,
        )
    )
    monkeypatch.setattr(health, "check_runtime_readiness", readiness_check)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {
            "database": "ok",
            "schema": "mismatch",
        },
    }
    assert "detail" not in response.json()


async def test_readiness_fails_closed_when_database_is_unavailable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness_check = AsyncMock(
        return_value=RuntimeReadinessReport(
            database=CheckState.UNAVAILABLE,
            schema=CheckState.NOT_CHECKED,
        )
    )
    monkeypatch.setattr(health, "check_runtime_readiness", readiness_check)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {
            "database": "unavailable",
            "schema": "not_checked",
        },
    }
    assert "detail" not in response.json()

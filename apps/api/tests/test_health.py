"""HTTP tests for liveness and readiness probes."""

from unittest.mock import AsyncMock

import pytest
from ai_governance_api.routers import health
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_legacy_health_remains_backward_compatible(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_liveness_does_not_require_dependency_checks(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness_check = AsyncMock(side_effect=AssertionError("must not be called"))
    monkeypatch.setattr(health, "check_database_readiness", readiness_check)

    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    readiness_check.assert_not_awaited()


@pytest.mark.asyncio
async def test_readiness_reports_database_available(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness_check = AsyncMock(return_value=True)
    monkeypatch.setattr(health, "check_database_readiness", readiness_check)

    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok"},
    }
    readiness_check.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_readiness_fails_closed_when_database_is_unavailable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness_check = AsyncMock(return_value=False)
    monkeypatch.setattr(health, "check_database_readiness", readiness_check)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "unavailable"},
    }
    assert "detail" not in response.json()
    readiness_check.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_database_probe_executes_against_test_database() -> None:
    assert await health.check_database_readiness() is True

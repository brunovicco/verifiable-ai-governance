import os
from collections.abc import AsyncIterator

os.environ["APP_ENV"] = "local"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["AUTO_CREATE_SCHEMA"] = "false"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["OIDC_ENABLED"] = "false"
os.environ["AUDIT_HASH_SALT"] = "test-salt"

import pytest_asyncio
from ai_governance_api.database import engine
from ai_governance_api.dependencies import get_runtime_control_projection
from ai_governance_api.main import app
from ai_governance_api.models import Base
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture(autouse=True)
async def reset_database() -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    projection = get_runtime_control_projection()
    await projection.close()
    get_runtime_control_projection.cache_clear()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client

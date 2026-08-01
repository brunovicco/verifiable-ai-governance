"""Asynchronous SQLAlchemy engine and request-scoped sessions."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from ai_governance_api.config import get_settings

settings = get_settings()
engine_options: dict[str, object] = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_options.update({"poolclass": StaticPool, "connect_args": {"check_same_thread": False}})

engine = create_async_engine(settings.database_url, **engine_options)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield one transaction-capable session per request."""
    async with SessionFactory() as session:
        yield session

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from ai_governance_api.adapters.runtime_readiness import (
    CheckState,
    check_runtime_readiness,
    load_expected_heads,
    resolve_alembic_config_path,
)
from ai_governance_api.database import engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
async def clean_alembic_version_table() -> AsyncIterator[None]:
    await _drop_alembic_version_table()
    yield
    await _drop_alembic_version_table()


async def test_database_without_version_table_is_not_ready(
    clean_alembic_version_table: None,
) -> None:
    report = await check_runtime_readiness(database_engine=engine)

    assert report.database is CheckState.OK
    assert report.schema is CheckState.MISMATCH
    assert report.ready is False


async def test_database_at_dynamic_alembic_heads_is_ready(
    clean_alembic_version_table: None,
) -> None:
    expected_heads = load_expected_heads()
    await _set_database_heads(expected_heads)

    report = await check_runtime_readiness(database_engine=engine)

    assert report.database is CheckState.OK
    assert report.schema is CheckState.OK
    assert report.ready is True


async def test_stale_database_revision_fails_closed(
    clean_alembic_version_table: None,
) -> None:
    await _set_database_heads({"stale-revision"})

    report = await check_runtime_readiness(database_engine=engine)

    assert report.database is CheckState.OK
    assert report.schema is CheckState.MISMATCH
    assert report.ready is False


async def test_missing_explicit_alembic_config_fails_before_database_access(
    tmp_path: Path,
) -> None:
    report = await check_runtime_readiness(
        database_engine=cast(AsyncEngine, _ExplodingEngine()),
        alembic_config_path=tmp_path / "missing-alembic.ini",
    )

    assert report.database is CheckState.NOT_CHECKED
    assert report.schema is CheckState.UNAVAILABLE
    assert report.ready is False


async def test_database_connection_failure_is_sanitized_and_fail_closed() -> None:
    report = await check_runtime_readiness(
        database_engine=cast(AsyncEngine, _FailingEngine()),
        alembic_config_path=resolve_alembic_config_path(),
    )

    assert report.database is CheckState.UNAVAILABLE
    assert report.schema is CheckState.NOT_CHECKED
    assert report.ready is False


async def test_database_readiness_timeout_fails_closed() -> None:
    report = await check_runtime_readiness(
        database_engine=cast(AsyncEngine, _SlowEngine()),
        alembic_config_path=resolve_alembic_config_path(),
        timeout_seconds=0.001,
    )

    assert report.database is CheckState.UNAVAILABLE
    assert report.schema is CheckState.NOT_CHECKED
    assert report.ready is False


async def _drop_alembic_version_table() -> None:
    async with engine.begin() as connection:
        await connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


async def _set_database_heads(heads: frozenset[str] | set[str]) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(255) NOT NULL PRIMARY KEY)"
            )
        )
        for head in sorted(heads):
            await connection.execute(
                text(
                    "INSERT INTO alembic_version (version_num) "
                    "VALUES (:version_num)"
                ),
                {"version_num": head},
            )


class _ExplodingEngine:
    def connect(self) -> None:
        raise AssertionError("database must not be accessed")


class _FailingConnectionContext:
    async def __aenter__(self) -> None:
        raise RuntimeError("sensitive database failure")

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


class _FailingEngine:
    def connect(self) -> _FailingConnectionContext:
        return _FailingConnectionContext()


class _SlowConnectionContext:
    async def __aenter__(self) -> None:
        await asyncio.sleep(1)

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


class _SlowEngine:
    def connect(self) -> _SlowConnectionContext:
        return _SlowConnectionContext()

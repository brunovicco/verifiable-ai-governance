"""PostgreSQL status-column contracts for shared governance enums."""

import asyncio
import os
from enum import StrEnum

import pytest
from governance_schemas import ApprovalStatus, EntityStatus
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

STATUS_COLUMNS: dict[tuple[str, str], type[StrEnum]] = {
    ("initiatives", "status"): EntityStatus,
    ("ai_systems", "status"): EntityStatus,
    ("model_assets", "status"): EntityStatus,
    ("agents", "status"): EntityStatus,
    ("assessments", "status"): EntityStatus,
    ("approvals", "status"): ApprovalStatus,
}


async def _status_column_lengths(
    database_url: str,
) -> dict[tuple[str, str], int | None]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    SELECT
                        table_name,
                        column_name,
                        character_maximum_length
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND column_name = 'status'
                    """
                )
            )
            return {
                (row.table_name, row.column_name): row.character_maximum_length for row in result
            }
    finally:
        await engine.dispose()


def test_postgres_status_columns_fit_current_enum_member_names() -> None:
    """Ensure migrated PostgreSQL columns can store every current enum name."""
    database_url = os.environ.get("DATABASE_URL", "")

    if not database_url.startswith("postgresql+asyncpg://"):
        pytest.skip("requires PostgreSQL through asyncpg")

    lengths = asyncio.run(_status_column_lengths(database_url))

    for column, enum_type in STATUS_COLUMNS.items():
        assert column in lengths

        actual_length = lengths[column]
        required_length = max(len(member.name) for member in enum_type)

        assert actual_length is not None
        assert actual_length >= required_length, (
            f"{column[0]}.{column[1]} allows {actual_length} characters "
            f"but {enum_type.__name__} requires {required_length}"
        )

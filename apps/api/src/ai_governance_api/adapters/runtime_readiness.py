"""Fail-closed runtime dependency and database-schema readiness checks."""

import asyncio
import logging
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_governance_api.config import get_settings
from ai_governance_api.database import engine

logger = logging.getLogger(__name__)

DEFAULT_READINESS_TIMEOUT_SECONDS = 2.0
ALEMBIC_CONFIG_ENVIRONMENT_VARIABLE = "ALEMBIC_CONFIG_PATH"


class CheckState(StrEnum):
    """Public state of one readiness check."""

    OK = "ok"
    UNAVAILABLE = "unavailable"
    MISMATCH = "mismatch"
    NOT_CHECKED = "not_checked"


@dataclass(frozen=True, slots=True)
class RuntimeReadinessReport:
    """Result of the bounded runtime readiness evaluation."""

    database: CheckState
    schema: CheckState
    runtime_control: CheckState = CheckState.NOT_CHECKED

    @property
    def ready(self) -> bool:
        """Return whether every required runtime check succeeded."""
        return (
            self.database is CheckState.OK
            and self.schema is CheckState.OK
            and self.runtime_control in {CheckState.OK, CheckState.NOT_CHECKED}
        )

    def public_checks(self) -> dict[str, str]:
        """Return stable checks, exposing runtime control only when configured."""
        checks = {
            "database": self.database.value,
            "schema": self.schema.value,
        }
        if self.runtime_control is not CheckState.NOT_CHECKED:
            checks["runtime_control"] = self.runtime_control.value
        return checks


def resolve_alembic_config_path(
    explicit_path: str | Path | None = None,
) -> Path:
    """Resolve the Alembic configuration used by the deployed API artifact."""
    if explicit_path is not None:
        return _require_existing_config(Path(explicit_path))

    configured_path = os.getenv(ALEMBIC_CONFIG_ENVIRONMENT_VARIABLE)
    if configured_path:
        return _require_existing_config(Path(configured_path))

    source_tree_path = Path(__file__).resolve().parents[3] / "alembic.ini"
    candidates = (
        Path.cwd() / "alembic.ini",
        Path.cwd() / "apps" / "api" / "alembic.ini",
        source_tree_path,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError("Alembic configuration could not be resolved")


def load_expected_heads(
    alembic_config_path: str | Path | None = None,
) -> frozenset[str]:
    """Load expected schema heads from Alembic's own revision graph."""
    config_path = resolve_alembic_config_path(alembic_config_path)
    config = Config(str(config_path))
    heads = frozenset(ScriptDirectory.from_config(config).get_heads())
    if not heads:
        raise RuntimeError("Alembic revision graph has no head")
    return heads


async def check_runtime_readiness(
    *,
    database_engine: AsyncEngine | None = None,
    alembic_config_path: str | Path | None = None,
    timeout_seconds: float = DEFAULT_READINESS_TIMEOUT_SECONDS,
) -> RuntimeReadinessReport:
    """Check database connectivity and exact Alembic-head compatibility."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    try:
        expected_heads = load_expected_heads(alembic_config_path)
    except Exception as exc:
        _log_readiness_failure("schema_configuration", exc)
        return RuntimeReadinessReport(
            database=CheckState.NOT_CHECKED,
            schema=CheckState.UNAVAILABLE,
        )

    selected_engine = database_engine or engine
    try:
        async with asyncio.timeout(timeout_seconds):
            async with selected_engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
                current_heads = frozenset(await connection.run_sync(_read_current_heads))
    except Exception as exc:
        _log_readiness_failure("database", exc)
        return RuntimeReadinessReport(
            database=CheckState.UNAVAILABLE,
            schema=CheckState.NOT_CHECKED,
        )

    if current_heads != expected_heads:
        logger.warning(
            "Runtime readiness check detected an incompatible database schema",
            extra={
                "readiness_check": "schema",
                "current_head_count": len(current_heads),
                "expected_head_count": len(expected_heads),
            },
        )
        return RuntimeReadinessReport(
            database=CheckState.OK,
            schema=CheckState.MISMATCH,
        )

    runtime_control = await _check_runtime_control(timeout_seconds=timeout_seconds)
    return RuntimeReadinessReport(
        database=CheckState.OK,
        schema=CheckState.OK,
        runtime_control=runtime_control,
    )


async def _check_runtime_control(*, timeout_seconds: float) -> CheckState:
    """Probe Redis only when distributed runtime control is enabled."""
    settings = get_settings()
    if not settings.runtime_control_enabled:
        return CheckState.NOT_CHECKED
    client = Redis.from_url(
        settings.runtime_control_redis_url,
        socket_connect_timeout=settings.runtime_control_redis_timeout_seconds,
        socket_timeout=settings.runtime_control_redis_timeout_seconds,
    )
    try:
        async with asyncio.timeout(timeout_seconds):
            await client.ping()
        return CheckState.OK
    except Exception as exc:
        _log_readiness_failure("runtime_control", exc)
        return CheckState.UNAVAILABLE
    finally:
        await client.aclose()


def _require_existing_config(path: Path) -> Path:
    """Return an existing Alembic config path or fail without fallback."""
    resolved_path = path.expanduser().resolve()
    if not resolved_path.is_file():
        raise FileNotFoundError("Configured Alembic file does not exist")
    return resolved_path


def _read_current_heads(connection: Connection) -> tuple[str, ...]:
    """Read current database heads through Alembic's migration context."""
    return tuple(MigrationContext.configure(connection).get_current_heads())


def _log_readiness_failure(check: str, exc: Exception) -> None:
    """Log failure metadata without connection strings or exception messages."""
    logger.warning(
        "Runtime readiness check failed",
        extra={
            "readiness_check": check,
            "error_type": type(exc).__name__,
        },
    )

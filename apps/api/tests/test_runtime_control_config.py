"""Configuration tests for distributed emergency runtime control."""

import pytest
from ai_governance_api.config import Settings
from pydantic import ValidationError


def test_local_runtime_control_accepts_redis_and_hides_credentials() -> None:
    settings = Settings(
        runtime_control_enabled=True,
        runtime_control_redis_url="redis://runtime-user:super-secret@localhost:6379/0",
    )

    assert settings.runtime_control_enabled is True
    assert "super-secret" not in repr(settings)


def test_shared_runtime_control_requires_tls() -> None:
    settings = Settings(
        runtime_control_enabled=True,
        runtime_control_redis_url="redis://localhost:6379/0",
    )

    with pytest.raises(ValueError, match="must use rediss"):
        settings._validate_runtime_control(require_tls=True)


def test_runtime_control_rejects_ambiguous_redis_url() -> None:
    with pytest.raises(ValidationError, match="must not contain a fragment"):
        Settings(
            runtime_control_enabled=True,
            runtime_control_redis_url="redis://localhost:6379/0#unsafe",
        )

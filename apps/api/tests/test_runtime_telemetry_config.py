import pytest
from ai_governance_api.config import Settings
from pydantic import ValidationError

AGENT_ID = "11111111-1111-4111-8111-111111111111"


def test_runtime_telemetry_api_keys_are_uuid_bound_and_secret_safe() -> None:
    settings = Settings(
        runtime_telemetry_ingest_enabled=True,
        runtime_telemetry_api_keys_json=f'{{"{AGENT_ID}":"secret-value"}}',
    )
    assert settings.runtime_telemetry_api_key_map == {AGENT_ID: "secret-value"}
    assert "secret-value" not in repr(settings)


def test_enabled_ingestion_requires_non_empty_valid_mapping() -> None:
    with pytest.raises(ValidationError, match="RUNTIME_TELEMETRY_API_KEYS_JSON"):
        Settings(runtime_telemetry_ingest_enabled=True)

    with pytest.raises(ValidationError, match="UUID"):
        Settings(
            runtime_telemetry_ingest_enabled=True,
            runtime_telemetry_api_keys_json='{"not-an-agent":"secret"}',
        )

"""Environment-driven application configuration."""

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    """Supported deployment environments."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Load deploy-specific configuration from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    app_name: str = "Verifiable AI Governance API"
    app_version: str = "0.1.0"
    app_env: AppEnvironment = AppEnvironment.LOCAL
    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    database_url: str = (
        "postgresql+asyncpg://governance:governance-local-only@localhost:5432/ai_governance"
    )
    auto_create_schema: bool = True
    cors_origins: str = "http://localhost:3000"
    cors_allow_credentials: bool = True

    oidc_enabled: bool = False
    dev_auth_enabled: bool = True
    oidc_issuer: str = ""
    oidc_audience: str = "ai-governance-api"
    oidc_algorithms: str = "RS256"
    oidc_groups_claim: str = "governance_areas"

    audit_hash_salt: str = Field(default="local-development-only", repr=False)
    control_catalog_path: str = ""

    evidence_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=50 * 1024 * 1024)
    evidence_request_overhead_bytes: int = Field(default=64 * 1024, ge=4096, le=1024 * 1024)
    evidence_allowed_content_types: str = (
        "application/pdf,image/png,image/jpeg,text/plain,text/csv,application/json"
    )
    malware_scanner_host: str = "localhost"
    malware_scanner_port: int = Field(default=3310, ge=1, le=65535)
    malware_scanner_connect_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    malware_scanner_scan_timeout_seconds: float = Field(default=30.0, gt=0, le=120)

    object_storage_endpoint_url: str = "http://localhost:9000"
    object_storage_region: str = "us-east-1"
    object_storage_bucket: str = "governance-evidence"
    object_storage_access_key: str = Field(default="", repr=False)
    object_storage_secret_key: str = Field(default="", repr=False)
    object_storage_auto_create_bucket: bool = True
    object_storage_server_side_encryption: str = ""
    object_storage_connect_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    object_storage_read_timeout_seconds: float = Field(default=30.0, gt=0, le=120)

    @property
    def cors_origin_list(self) -> list[str]:
        """Return normalized CORS origins from the comma-separated setting."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def oidc_algorithm_list(self) -> list[str]:
        """Return normalized asymmetric JWT algorithms."""
        return [
            algorithm.strip() for algorithm in self.oidc_algorithms.split(",") if algorithm.strip()
        ]

    @property
    def evidence_allowed_content_type_set(self) -> frozenset[str]:
        """Return the normalized evidence media-type allowlist."""
        return frozenset(
            content_type.strip().lower()
            for content_type in self.evidence_allowed_content_types.split(",")
            if content_type.strip()
        )

    @model_validator(mode="after")
    def validate_authentication(self) -> "Settings":
        """Fail closed when deployment settings weaken authentication or audit."""
        is_local = self.app_env in {AppEnvironment.LOCAL, AppEnvironment.TEST}
        if not is_local and not self.oidc_enabled:
            raise ValueError("OIDC must be enabled outside the local environment")
        if self.oidc_enabled and not self.oidc_issuer:
            raise ValueError("OIDC_ISSUER is required when OIDC is enabled")
        if not self.oidc_algorithm_list or any(
            algorithm.lower() == "none" for algorithm in self.oidc_algorithm_list
        ):
            raise ValueError("OIDC_ALGORITHMS must contain trusted signing algorithms")
        if not is_local and self.dev_auth_enabled:
            raise ValueError("DEV_AUTH_ENABLED must be false outside local and test environments")
        if not is_local and self.auto_create_schema:
            raise ValueError("AUTO_CREATE_SCHEMA must be false outside local and test environments")
        if not is_local and self.audit_hash_salt == "local-development-only":
            raise ValueError("AUDIT_HASH_SALT must be changed outside the local environment")
        if not self.cors_origin_list:
            raise ValueError("CORS_ORIGINS must define at least one origin")
        if not is_local and "*" in self.cors_origin_list:
            raise ValueError("Wildcard CORS origins are not allowed outside local environments")
        if self.cors_allow_credentials and "*" in self.cors_origin_list:
            raise ValueError("Credentialed CORS cannot use a wildcard origin")
        if not self.evidence_allowed_content_type_set:
            raise ValueError("EVIDENCE_ALLOWED_CONTENT_TYPES must not be empty")
        if bool(self.object_storage_access_key) != bool(self.object_storage_secret_key):
            raise ValueError("Object-storage access and secret keys must be configured together")
        if not is_local and self.object_storage_auto_create_bucket:
            raise ValueError("OBJECT_STORAGE_AUTO_CREATE_BUCKET must be false outside local")
        if not is_local and not self.object_storage_server_side_encryption:
            raise ValueError("Object-storage encryption is required outside local")
        if (
            not is_local
            and self.object_storage_endpoint_url
            and not self.object_storage_endpoint_url.startswith("https://")
        ):
            raise ValueError("Explicit object-storage endpoints must use HTTPS outside local")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable settings snapshot."""
    return Settings()

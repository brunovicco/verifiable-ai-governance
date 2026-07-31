from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Verifiable AI Governance API"
    app_env: str = "local"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+asyncpg://governance:governance-local-only@localhost:5432/ai_governance"
    )
    auto_create_schema: bool = True
    cors_origins: str = "http://localhost:3000"

    oidc_enabled: bool = False
    dev_auth_enabled: bool = True
    oidc_issuer: str = ""
    oidc_audience: str = "ai-governance-api"
    oidc_algorithms: str = "RS256"
    oidc_groups_claim: str = "governance_areas"

    audit_hash_salt: str = Field(default="local-development-only", repr=False)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_authentication(self) -> "Settings":
        if self.app_env != "local" and not self.oidc_enabled:
            raise ValueError("OIDC must be enabled outside the local environment")
        if self.oidc_enabled and not self.oidc_issuer:
            raise ValueError("OIDC_ISSUER is required when OIDC is enabled")
        if self.app_env != "local" and self.audit_hash_salt == "local-development-only":
            raise ValueError("AUDIT_HASH_SALT must be changed outside the local environment")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

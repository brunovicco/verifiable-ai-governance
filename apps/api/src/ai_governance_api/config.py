"""Environment-driven application configuration."""

import json
from enum import StrEnum
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

TRUSTED_OIDC_ALGORITHMS = frozenset(
    {
        "RS256",
        "RS384",
        "RS512",
        "PS256",
        "PS384",
        "PS512",
        "ES256",
        "ES384",
        "ES512",
        "EdDSA",
    }
)


class AppEnvironment(StrEnum):
    """Supported deployment environments."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class OidcIdentityMode(StrEnum):
    """Supported verified-claim identity mapping strategies."""

    SUBJECT = "subject"
    ENTRA = "entra"


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
    oidc_jwks_url: str = ""
    oidc_audience: str = "ai-governance-api"
    oidc_algorithms: str = "RS256"
    oidc_groups_claim: str = "governance_areas"
    oidc_admin_claim: str = "governance_admin"
    oidc_identity_mode: OidcIdentityMode = OidcIdentityMode.SUBJECT
    oidc_allowed_tenant_ids: str = ""
    oidc_guest_approvals_enabled: bool = False
    oidc_entra_app_roles_claim: str = "roles"
    oidc_entra_groups_claim: str = "groups"
    oidc_jwks_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    oidc_jwks_cache_seconds: float = Field(default=300, ge=30, le=86400)
    oidc_clock_skew_seconds: float = Field(default=30, ge=0, le=300)
    oidc_max_token_length: int = Field(default=16384, ge=1024, le=65536)

    microsoft_graph_enabled: bool = False
    microsoft_graph_client_id: str = ""
    microsoft_graph_client_secret: str = Field(default="", repr=False)
    microsoft_graph_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    microsoft_graph_max_pages: int = Field(default=20, ge=1, le=100)
    microsoft_graph_max_attempts: int = Field(default=3, ge=1, le=5)
    microsoft_graph_backoff_base_seconds: float = Field(default=0.25, gt=0, le=5)
    microsoft_graph_max_retry_delay_seconds: float = Field(default=2.0, gt=0, le=30)
    microsoft_graph_max_retry_after_seconds: int = Field(default=300, ge=0, le=3600)
    microsoft_graph_max_response_bytes: int = Field(
        default=1024 * 1024,
        ge=1024,
        le=5 * 1024 * 1024,
    )
    directory_authorization_catalog_path: str = ""
    directory_authorization_cache_ttl_seconds: int = Field(
        default=60,
        ge=5,
        le=300,
    )

    policy_model_router_enabled: bool = False
    policy_model_router_base_url: str = "http://localhost:8082"
    policy_model_router_api_keys_json: str = Field(default="{}", repr=False)
    policy_model_router_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    policy_model_router_max_response_bytes: int = Field(
        default=256 * 1024,
        ge=1024,
        le=1024 * 1024,
    )

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
    def oidc_allowed_tenant_id_set(self) -> frozenset[str]:
        """Return canonical non-nil tenant UUIDs from the deployment allowlist."""
        tenant_ids: set[str] = set()
        for raw_value in self.oidc_allowed_tenant_ids.split(","):
            value = raw_value.strip()
            if not value:
                continue
            try:
                tenant_id = UUID(value)
            except ValueError as exc:
                raise ValueError("OIDC_ALLOWED_TENANT_IDS must contain only UUIDs") from exc
            if tenant_id.int == 0:
                raise ValueError("OIDC_ALLOWED_TENANT_IDS must contain only non-nil UUIDs")
            tenant_ids.add(str(tenant_id))
        return frozenset(tenant_ids)

    @property
    def oidc_entra_issuer_tenant_id(self) -> str:
        """Return the canonical tenant UUID bound to the Entra issuer."""
        parsed = urlparse(self.oidc_issuer)
        path = [segment for segment in parsed.path.split("/") if segment]
        if (
            parsed.scheme != "https"
            or parsed.netloc != "login.microsoftonline.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or len(path) != 2
            or path[1] != "v2.0"
        ):
            raise ValueError(
                "OIDC_ISSUER must be a tenant-specific Microsoft Entra v2 issuer"
            )
        try:
            return str(UUID(path[0]))
        except ValueError as exc:
            raise ValueError(
                "OIDC_ISSUER must contain an explicit Microsoft Entra tenant UUID"
            ) from exc

    @property
    def evidence_allowed_content_type_set(self) -> frozenset[str]:
        """Return the normalized evidence media-type allowlist."""
        return frozenset(
            content_type.strip().lower()
            for content_type in self.evidence_allowed_content_types.split(",")
            if content_type.strip()
        )

    @property
    def policy_model_router_api_key_map(self) -> dict[str, str]:
        """Return the validated per-agent secret mapping for policy-model-router."""
        try:
            raw = json.loads(self.policy_model_router_api_keys_json)
        except json.JSONDecodeError as exc:
            raise ValueError("POLICY_MODEL_ROUTER_API_KEYS_JSON must be valid JSON") from exc
        if not isinstance(raw, dict):
            raise ValueError("POLICY_MODEL_ROUTER_API_KEYS_JSON must be a JSON object")
        api_keys: dict[str, str] = {}
        for agent_name, api_key in raw.items():
            if (
                not isinstance(agent_name, str)
                or not isinstance(api_key, str)
                or not agent_name
                or agent_name != agent_name.strip()
                or len(agent_name) > 200
                or not api_key
            ):
                raise ValueError(
                    "POLICY_MODEL_ROUTER_API_KEYS_JSON must map bounded agent names to secrets"
                )
            api_keys[agent_name] = api_key
        return api_keys

    @model_validator(mode="after")
    def validate_authentication(self) -> "Settings":
        """Fail closed when deployment settings weaken authentication or audit."""
        is_local = self.app_env in {AppEnvironment.LOCAL, AppEnvironment.TEST}
        if not is_local and not self.oidc_enabled:
            raise ValueError("OIDC must be enabled outside the local environment")
        if self.oidc_enabled and not self.oidc_issuer:
            raise ValueError("OIDC_ISSUER is required when OIDC is enabled")
        if self.oidc_enabled and not self.oidc_jwks_url:
            raise ValueError("OIDC_JWKS_URL is required when OIDC is enabled")
        if not self.oidc_algorithm_list or any(
            algorithm not in TRUSTED_OIDC_ALGORITHMS for algorithm in self.oidc_algorithm_list
        ):
            raise ValueError("OIDC_ALGORITHMS must contain only trusted asymmetric algorithms")
        if self.oidc_enabled:
            self._validate_oidc_url("OIDC_ISSUER", self.oidc_issuer, require_tls=not is_local)
            self._validate_oidc_url("OIDC_JWKS_URL", self.oidc_jwks_url, require_tls=not is_local)
            if not self.oidc_audience.strip():
                raise ValueError("OIDC_AUDIENCE must not be empty")
            if not self.oidc_groups_claim.strip() or not self.oidc_admin_claim.strip():
                raise ValueError("OIDC claim paths must not be empty")
            if self.oidc_identity_mode is OidcIdentityMode.ENTRA:
                self._validate_entra_identity_boundary()
            elif self.oidc_allowed_tenant_ids.strip() or self.oidc_guest_approvals_enabled:
                raise ValueError(
                    "Entra tenant and guest settings require OIDC_IDENTITY_MODE=entra"
                )
        if self.microsoft_graph_enabled:
            self._validate_microsoft_graph()
        if self.policy_model_router_enabled:
            self._validate_policy_model_router(require_tls=not is_local)
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

    def _validate_policy_model_router(self, *, require_tls: bool) -> None:
        """Require a trusted URL and at least one per-agent routing credential."""
        self._validate_oidc_url(
            "POLICY_MODEL_ROUTER_BASE_URL",
            self.policy_model_router_base_url,
            require_tls=require_tls,
        )
        parsed = urlparse(self.policy_model_router_base_url)
        if (
            parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(
                "POLICY_MODEL_ROUTER_BASE_URL must not contain credentials, query, or fragment"
            )
        if not self.policy_model_router_api_key_map:
            raise ValueError(
                "POLICY_MODEL_ROUTER_API_KEYS_JSON is required when policy routing is enabled"
            )

    def _validate_entra_identity_boundary(self) -> None:
        """Require tenant-specific Entra trust coherent with the tenant allowlist."""
        if (
            not self.oidc_entra_app_roles_claim.strip()
            or not self.oidc_entra_groups_claim.strip()
        ):
            raise ValueError("OIDC Entra claim paths must not be empty")
        allowed_tenants = self.oidc_allowed_tenant_id_set
        if not allowed_tenants:
            raise ValueError("OIDC_ALLOWED_TENANT_IDS is required in Entra identity mode")
        issuer_tenant = self.oidc_entra_issuer_tenant_id
        if issuer_tenant not in allowed_tenants:
            raise ValueError("OIDC_ISSUER tenant must be present in OIDC_ALLOWED_TENANT_IDS")

    def _validate_microsoft_graph(self) -> None:
        """Require Graph OBO to use the established tenant-specific Entra boundary."""
        if not self.oidc_enabled or self.oidc_identity_mode is not OidcIdentityMode.ENTRA:
            raise ValueError(
                "Microsoft Graph requires OIDC_ENABLED=true and OIDC_IDENTITY_MODE=entra"
            )
        try:
            client_id = UUID(self.microsoft_graph_client_id.strip())
        except (ValueError, AttributeError) as exc:
            raise ValueError("MICROSOFT_GRAPH_CLIENT_ID must be a UUID") from exc
        if client_id.int == 0:
            raise ValueError("MICROSOFT_GRAPH_CLIENT_ID must be a non-nil UUID")
        if not self.microsoft_graph_client_secret.strip():
            raise ValueError(
                "MICROSOFT_GRAPH_CLIENT_SECRET is required when Microsoft Graph is enabled"
            )

    @staticmethod
    def _validate_oidc_url(name: str, value: str, *, require_tls: bool) -> None:
        """Validate an explicit OIDC trust URL and prohibit embedded credentials."""
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"{name} must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError(f"{name} must not contain credentials")
        if require_tls and parsed.scheme != "https":
            raise ValueError(f"{name} must use HTTPS outside local and test environments")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable settings snapshot."""
    return Settings()

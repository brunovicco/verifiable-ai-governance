"""Deployment adapter for Governance runtime authorization issuance."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_governance_api.adapters.runtime_authorization_crypto import (
    PyJwtEd25519SignatureProvider,
)
from ai_governance_api.application.runtime_authorization_issuance import (
    GovernanceRuntimeAuthorizationIssuer,
    RuntimeAuthorizationIssuancePolicy,
)
from ai_governance_api.application.runtime_authorization_security import (
    RuntimeAuthorizationSigner,
)
from ai_governance_api.domain.runtime_authorization_security import (
    RuntimeAuthorizationSigningKey,
    load_runtime_authorization_key_set_json,
)


class RuntimeAuthorizationIssuanceSettings(BaseSettings):
    """Secret and provenance configuration for signing runtime authorization."""

    model_config = SettingsConfigDict(
        env_prefix="RUNTIME_AUTHORIZATION_",
        frozen=True,
        extra="ignore",
    )

    issuer: str = "verifiable-ai-governance:production"
    audience: str = "policy-model-router,multi-agent-credit-desk"
    lifetime_seconds: int = Field(default=300, ge=1, le=600)
    signing_kid: str = ""
    private_key_path: Path | None = None
    trusted_key_set_path: Path | None = None
    max_private_key_bytes: int = Field(default=16_384, ge=1024, le=65_536)
    max_key_set_bytes: int = Field(default=262_144, ge=1024, le=2_097_152)

    policy_id: str = "baseline-governance-policy"
    policy_version: str = "1.0.0"
    policy_digest: str = ""
    control_catalog_id: str = "verifiable-ai-governance-baseline"
    control_catalog_version: str = "1.0.0"
    control_catalog_digest: str = ""

    @field_validator("private_key_path", "trusted_key_set_path", mode="before")
    @classmethod
    def _blank_path_means_unset(cls, value: object) -> object:
        """Treat a blank environment value as missing."""
        return None if value == "" else value

    @property
    def audience_tuple(self) -> tuple[str, ...]:
        """Return canonical non-empty audiences."""
        values = tuple(
            sorted({value.strip() for value in self.audience.split(",") if value.strip()})
        )
        if not values:
            raise ValueError("RUNTIME_AUTHORIZATION_AUDIENCE must not be empty")
        return values


@lru_cache
def build_runtime_authorization_issuer() -> GovernanceRuntimeAuthorizationIssuer:
    """Load signing material and construct the process-wide issuer."""
    settings = RuntimeAuthorizationIssuanceSettings()
    _validate_settings(settings)
    assert settings.private_key_path is not None
    assert settings.trusted_key_set_path is not None

    private_key_pem = _read_bounded_text(
        settings.private_key_path,
        max_bytes=settings.max_private_key_bytes,
        label="private signing key",
    )
    key_set_json = _read_bounded_text(
        settings.trusted_key_set_path,
        max_bytes=settings.max_key_set_bytes,
        label="trusted public key set",
    )
    key_set = load_runtime_authorization_key_set_json(key_set_json)
    signer = RuntimeAuthorizationSigner(
        RuntimeAuthorizationSigningKey(
            kid=settings.signing_kid,
            private_key_pem=private_key_pem,
        ),
        key_set,
        PyJwtEd25519SignatureProvider(),
        issuer=settings.issuer,
    )
    policy = RuntimeAuthorizationIssuancePolicy(
        issuer=settings.issuer,
        audience=settings.audience_tuple,
        lifetime_seconds=settings.lifetime_seconds,
        policy_id=settings.policy_id,
        policy_version=settings.policy_version,
        policy_digest=settings.policy_digest,
        control_catalog_id=settings.control_catalog_id,
        control_catalog_version=settings.control_catalog_version,
        control_catalog_digest=settings.control_catalog_digest,
    )
    return GovernanceRuntimeAuthorizationIssuer(signer, policy)


def _validate_settings(settings: RuntimeAuthorizationIssuanceSettings) -> None:
    required_strings = {
        "RUNTIME_AUTHORIZATION_SIGNING_KID": settings.signing_kid,
        "RUNTIME_AUTHORIZATION_POLICY_DIGEST": settings.policy_digest,
        "RUNTIME_AUTHORIZATION_CONTROL_CATALOG_DIGEST": (settings.control_catalog_digest),
    }
    for name, value in required_strings.items():
        if not value.strip():
            raise RuntimeError(f"{name} is required")
    for name, value in {
        "RUNTIME_AUTHORIZATION_POLICY_DIGEST": settings.policy_digest,
        "RUNTIME_AUTHORIZATION_CONTROL_CATALOG_DIGEST": (settings.control_catalog_digest),
    }.items():
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise RuntimeError(f"{name} must be a lowercase SHA-256 digest")
    if settings.private_key_path is None:
        raise RuntimeError("RUNTIME_AUTHORIZATION_PRIVATE_KEY_PATH is required")
    if settings.trusted_key_set_path is None:
        raise RuntimeError("RUNTIME_AUTHORIZATION_TRUSTED_KEY_SET_PATH is required")


def _read_bounded_text(path: Path, *, max_bytes: int, label: str) -> str:
    """Read a bounded UTF-8 deployment secret/config file."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"Runtime authorization {label} is unavailable") from exc
    if len(raw) > max_bytes:
        raise RuntimeError(f"Runtime authorization {label} is too large")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"Runtime authorization {label} must be UTF-8") from exc

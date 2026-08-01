"""Fail-closed YAML loader for the Entra authorization mapping catalog."""

from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from governance_schemas import ApprovalArea
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr, ValidationError

from ai_governance_api.domain.directory_authorization import (
    DirectoryAuthorizationCatalog,
    DirectoryAuthorizationError,
    DirectoryAuthorizationMapping,
    DirectoryAuthorizationSource,
)

MAX_CATALOG_BYTES = 1024 * 1024


class DirectoryAuthorizationCatalogError(ValueError):
    """Raised when the configured authorization catalog cannot be trusted."""


class _MappingPayload(BaseModel):
    """Strict transport schema for one YAML mapping record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mapping_id: StrictStr
    tenant_id: StrictStr
    source_type: StrictStr
    source_value: StrictStr
    approval_area: StrictStr
    enabled: StrictBool
    owner: StrictStr
    mapping_version: StrictInt


class _CatalogPayload(BaseModel):
    """Strict transport schema for the versioned YAML catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    catalog_id: StrictStr
    catalog_version: StrictStr
    mappings: list[_MappingPayload]


class YamlDirectoryAuthorizationCatalog:
    """Load a validated immutable authorization catalog from YAML."""

    @classmethod
    def from_package(cls) -> DirectoryAuthorizationCatalog:
        """Load the fail-closed catalog bundled with the API package."""
        resource = files("ai_governance_api").joinpath(
            "directory_authorization_catalog.yaml"
        )
        try:
            content = resource.read_text(encoding="utf-8")
        except OSError as exc:
            raise DirectoryAuthorizationCatalogError(
                "Packaged directory authorization catalog could not be read"
            ) from exc
        return cls.from_yaml(content)

    @classmethod
    def from_path(cls, path: str | Path) -> DirectoryAuthorizationCatalog:
        """Load an explicit catalog without fallback when configuration fails."""
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise DirectoryAuthorizationCatalogError(
                "Configured directory authorization catalog could not be read"
            ) from exc
        return cls.from_yaml(content)

    @staticmethod
    def from_yaml(content: str) -> DirectoryAuthorizationCatalog:
        """Parse strict YAML into the framework-independent catalog model."""
        if len(content.encode("utf-8")) > MAX_CATALOG_BYTES:
            raise DirectoryAuthorizationCatalogError(
                "Directory authorization catalog exceeds its size limit"
            )
        try:
            raw: Any = yaml.safe_load(content)
            payload = _CatalogPayload.model_validate(raw, strict=True)
            mappings = tuple(
                DirectoryAuthorizationMapping(
                    mapping_id=mapping.mapping_id,
                    tenant_id=mapping.tenant_id,
                    source_type=DirectoryAuthorizationSource(mapping.source_type),
                    source_value=mapping.source_value,
                    approval_area=ApprovalArea(mapping.approval_area),
                    enabled=mapping.enabled,
                    owner=mapping.owner,
                    mapping_version=mapping.mapping_version,
                )
                for mapping in payload.mappings
            )
            return DirectoryAuthorizationCatalog(
                catalog_id=payload.catalog_id,
                catalog_version=payload.catalog_version,
                mappings=mappings,
            )
        except (
            yaml.YAMLError,
            ValidationError,
            DirectoryAuthorizationError,
            ValueError,
            TypeError,
        ) as exc:
            raise DirectoryAuthorizationCatalogError(
                "Directory authorization catalog validation failed"
            ) from exc

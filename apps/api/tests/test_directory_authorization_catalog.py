from pathlib import Path

import pytest
from ai_governance_api.adapters.directory_authorization_catalog import (
    DirectoryAuthorizationCatalogError,
    YamlDirectoryAuthorizationCatalog,
)
from ai_governance_api.domain.directory_authorization import DirectoryAuthorizationSource
from governance_schemas import ApprovalArea

VALID_YAML = """
catalog_id: enterprise-entra-authorization
catalog_version: "2026.08.1"
mappings:
  - mapping_id: entra-security-reviewer
    tenant_id: 11111111-1111-4111-8111-111111111111
    source_type: app_role
    source_value: Governance.Security.Reviewer
    approval_area: security
    enabled: true
    owner: identity-and-access-management
    mapping_version: 1
"""


def test_packaged_catalog_is_empty_and_fail_closed() -> None:
    catalog = YamlDirectoryAuthorizationCatalog.from_package()

    assert catalog.catalog_id == "enterprise-entra-authorization"
    assert catalog.catalog_version == "2026.08.1"
    assert catalog.mappings == ()


def test_yaml_loader_builds_strict_versioned_mapping() -> None:
    catalog = YamlDirectoryAuthorizationCatalog.from_yaml(VALID_YAML)

    assert len(catalog.mappings) == 1
    item = catalog.mappings[0]
    assert item.source_type is DirectoryAuthorizationSource.APP_ROLE
    assert item.approval_area is ApprovalArea.SECURITY
    assert item.mapping_version == 1


@pytest.mark.parametrize(
    "content",
    [
        VALID_YAML.replace("enabled: true", 'enabled: "true"'),
        VALID_YAML.replace("mapping_version: 1", 'mapping_version: "1"'),
        VALID_YAML.replace("mapping_version: 1", "mapping_version: 1\n    unexpected: value"),
        VALID_YAML.replace("source_type: app_role", "source_type: display_name"),
        VALID_YAML.replace("approval_area: security", "approval_area: superuser"),
    ],
)
def test_yaml_loader_rejects_ambiguous_or_unknown_values(content: str) -> None:
    with pytest.raises(DirectoryAuthorizationCatalogError, match="validation failed"):
        YamlDirectoryAuthorizationCatalog.from_yaml(content)


def test_configured_catalog_path_does_not_fallback(tmp_path: Path) -> None:
    with pytest.raises(DirectoryAuthorizationCatalogError, match="could not be read"):
        YamlDirectoryAuthorizationCatalog.from_path(tmp_path / "missing.yaml")


def test_yaml_loader_rejects_oversized_catalog() -> None:
    with pytest.raises(DirectoryAuthorizationCatalogError, match="size limit"):
        YamlDirectoryAuthorizationCatalog.from_yaml("x" * (1024 * 1024 + 1))

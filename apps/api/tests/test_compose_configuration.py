from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[3]
CLAMAV_MULTI_ARCH_IMAGE = (
    "clamav/clamav-debian:1.4.5@"
    "sha256:50296b62b23764b474be18310521f64a720524d69334ea5236aab5fac44ff993"
)


def test_clamav_image_is_pinned_to_official_multi_arch_index() -> None:
    compose = cast(
        dict[str, Any],
        yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8")),
    )

    scanner = compose["services"]["malware-scanner"]

    assert scanner["image"] == CLAMAV_MULTI_ARCH_IMAGE
    assert scanner["ports"] == ["127.0.0.1:${CLAMAV_PORT:-3310}:3310"]
    assert scanner["volumes"] == ["governance-clamav:/var/lib/clamav"]


def test_api_waits_for_explicit_successful_migration() -> None:
    compose = cast(
        dict[str, Any],
        yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8")),
    )

    migration = compose["services"]["migrate"]
    api = compose["services"]["api"]

    assert migration["command"] == [
        "alembic",
        "-c",
        "/workspace/alembic.ini",
        "upgrade",
        "head",
    ]
    assert migration["environment"]["AUTO_CREATE_SCHEMA"] == "false"
    assert api["environment"]["AUTO_CREATE_SCHEMA"] == "false"
    assert api["depends_on"]["migrate"] == {
        "condition": "service_completed_successfully"
    }


def test_web_authentication_build_configuration_is_explicit() -> None:
    compose = cast(
        dict[str, Any],
        yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8")),
    )

    web = compose["services"]["web"]
    expected_public_configuration = {
        "NEXT_PUBLIC_AUTH_MODE": "${NEXT_PUBLIC_AUTH_MODE:-local}",
        "NEXT_PUBLIC_ENTRA_CLIENT_ID": "${NEXT_PUBLIC_ENTRA_CLIENT_ID:-}",
        "NEXT_PUBLIC_ENTRA_TENANT_ID": "${NEXT_PUBLIC_ENTRA_TENANT_ID:-}",
        "NEXT_PUBLIC_ENTRA_API_SCOPE": "${NEXT_PUBLIC_ENTRA_API_SCOPE:-}",
    }

    for name, value in expected_public_configuration.items():
        assert web["build"]["args"][name] == value
        assert web["environment"][name] == value


def test_api_corporate_identity_policy_is_environment_driven() -> None:
    """Keep tenant and guest policy explicit at the API composition root."""
    compose = cast(
        dict[str, Any],
        yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8")),
    )

    environment = compose["x-api-environment"]

    assert environment["OIDC_IDENTITY_MODE"] == "${OIDC_IDENTITY_MODE:-subject}"
    assert environment["OIDC_ALLOWED_TENANT_IDS"] == "${OIDC_ALLOWED_TENANT_IDS:-}"
    assert environment["OIDC_GUEST_APPROVALS_ENABLED"] == (
        "${OIDC_GUEST_APPROVALS_ENABLED:-false}"
    )
    assert environment["OIDC_ENTRA_APP_ROLES_CLAIM"] == (
        "${OIDC_ENTRA_APP_ROLES_CLAIM:-roles}"
    )
    assert environment["OIDC_ENTRA_GROUPS_CLAIM"] == (
        "${OIDC_ENTRA_GROUPS_CLAIM:-groups}"
    )
    assert environment["DIRECTORY_AUTHORIZATION_CATALOG_PATH"] == (
        "${DIRECTORY_AUTHORIZATION_CATALOG_PATH:-}"
    )


def test_api_graph_obo_configuration_is_environment_driven() -> None:
    """Keep Graph OBO opt-in and its secret out of committed defaults."""
    compose = cast(
        dict[str, Any],
        yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8")),
    )

    environment = compose["x-api-environment"]

    assert environment["MICROSOFT_GRAPH_ENABLED"] == "${MICROSOFT_GRAPH_ENABLED:-false}"
    assert environment["MICROSOFT_GRAPH_CLIENT_ID"] == "${MICROSOFT_GRAPH_CLIENT_ID:-}"
    assert environment["MICROSOFT_GRAPH_CLIENT_SECRET"] == (
        "${MICROSOFT_GRAPH_CLIENT_SECRET:-}"
    )
    assert environment["MICROSOFT_GRAPH_MAX_ATTEMPTS"] == (
        "${MICROSOFT_GRAPH_MAX_ATTEMPTS:-3}"
    )
    assert environment["MICROSOFT_GRAPH_BACKOFF_BASE_SECONDS"] == (
        "${MICROSOFT_GRAPH_BACKOFF_BASE_SECONDS:-0.25}"
    )
    assert environment["MICROSOFT_GRAPH_MAX_RETRY_DELAY_SECONDS"] == (
        "${MICROSOFT_GRAPH_MAX_RETRY_DELAY_SECONDS:-2}"
    )
    assert environment["MICROSOFT_GRAPH_MAX_RESPONSE_BYTES"] == (
        "${MICROSOFT_GRAPH_MAX_RESPONSE_BYTES:-1048576}"
    )

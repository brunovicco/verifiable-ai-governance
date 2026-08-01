"""Validate real OIDC token issuance, claim mapping, and API rejection paths."""

import json
import os
import time
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8081").rstrip("/")
API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
CLIENT_ID = os.getenv("OIDC_TEST_CLIENT_ID", "ai-governance-cli")
USERNAME = os.getenv("OIDC_TEST_USERNAME", "security.reviewer")
PASSWORD = os.getenv("OIDC_TEST_PASSWORD", "local-only")
EXPECTED_AREA = os.getenv("OIDC_TEST_EXPECTED_AREA", "security")


def request_json(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 3,
) -> tuple[int, dict[str, Any]]:
    """Perform one bounded HTTP request and decode its JSON response."""
    request = Request(url, data=data, headers=dict(headers or {}), method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body) if body else {}


def wait_until_ready(url: str, *, attempts: int = 60) -> None:
    """Wait for a local validation endpoint using a finite retry budget."""
    for _ in range(attempts):
        try:
            status, _ = request_json(url)
            if status == 200:
                return
        except (URLError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for {url}")


def obtain_access_token() -> str:
    """Obtain a short-lived local test-user access token from Keycloak."""
    form = urlencode(
        {
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "username": USERNAME,
            "password": PASSWORD,
        }
    ).encode("utf-8")
    status, payload = request_json(
        f"{KEYCLOAK_URL}/realms/ai-governance/protocol/openid-connect/token",
        method="POST",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    access_token = payload.get("access_token")
    if status != 200 or not isinstance(access_token, str):
        raise RuntimeError(f"Keycloak token request failed with HTTP {status}")
    return access_token


def authenticated_identity(access_token: str) -> tuple[int, dict[str, Any]]:
    """Call the principal inspection endpoint with one bearer token."""
    return request_json(
        f"{API_URL}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )


def tamper_signature(access_token: str) -> str:
    """Change signed bytes while retaining a structurally valid JWT."""
    header, payload, signature = access_token.split(".")
    first = "A" if signature[0] != "A" else "B"
    return ".".join((header, payload, first + signature[1:]))


def main() -> int:
    """Run the real-provider integration checks and fail on any unsafe result."""
    wait_until_ready(f"{KEYCLOAK_URL}/realms/ai-governance/.well-known/openid-configuration")
    wait_until_ready(f"{API_URL}/health")
    access_token = obtain_access_token()

    status, identity = authenticated_identity(access_token)
    if status != 200:
        raise RuntimeError(f"API rejected a valid Keycloak token with HTTP {status}")
    user_id = identity.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        raise RuntimeError("API did not map the stable OIDC subject")
    if identity.get("email") != f"{USERNAME}@example.test":
        raise RuntimeError("API mapped an unexpected OIDC identity")
    if EXPECTED_AREA not in identity.get("approval_areas", []):
        raise RuntimeError("API did not map the expected governance area")
    if identity.get("is_admin") is not False:
        raise RuntimeError("API granted an unexpected administrative capability")

    missing_status, _ = request_json(f"{API_URL}/api/v1/auth/me")
    if missing_status != 401:
        raise RuntimeError("API did not reject a missing bearer token")

    tampered_status, _ = authenticated_identity(tamper_signature(access_token))
    if tampered_status != 401:
        raise RuntimeError("API did not reject a token with a tampered signature")

    print("OIDC validation passed: real token, group mapping, and rejection paths verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

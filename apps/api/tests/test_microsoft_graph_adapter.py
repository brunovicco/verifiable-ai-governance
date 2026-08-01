from collections.abc import Callable
from urllib.parse import parse_qs

import httpx
import pytest
from ai_governance_api.adapters.microsoft_graph import (
    GRAPH_GROUPS_URL,
    GRAPH_ME_URL,
    GRAPH_SCOPE,
    OBO_GRANT_TYPE,
    PROFILE_SELECT,
    MicrosoftGraphCorporateDirectory,
)
from ai_governance_api.application.corporate_directory import (
    CorporateDirectoryResponseInvalid,
    CorporateDirectoryUnavailable,
)
from ai_governance_api.domain.identity import DirectoryAccountType, DirectoryIdentity

TENANT_ID = "11111111-1111-4111-8111-111111111111"
CLIENT_ID = "22222222-2222-4222-8222-222222222222"
USER_ID = "33333333-3333-4333-8333-333333333333"
GROUP_ONE = "44444444-4444-4444-8444-444444444444"
GROUP_TWO = "55555555-5555-4555-8555-555555555555"
TOKEN_PATH = f"/{TENANT_ID}/oauth2/v2.0/token"


def directory(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_pages: int = 5,
    max_retry_after_seconds: int = 120,
) -> MicrosoftGraphCorporateDirectory:
    return MicrosoftGraphCorporateDirectory(
        tenant_id=TENANT_ID,
        client_id=CLIENT_ID,
        client_secret="test-client-secret",
        timeout_seconds=1,
        max_pages=max_pages,
        max_retry_after_seconds=max_retry_after_seconds,
        max_response_bytes=1024 * 1024,
        transport=httpx.MockTransport(handler),
    )


def expected_identity() -> DirectoryIdentity:
    return DirectoryIdentity(
        tenant_id=TENANT_ID,
        object_id=USER_ID,
        account_type=DirectoryAccountType.MEMBER,
    )


def token_response(request: httpx.Request) -> httpx.Response:
    assert request.method == "POST"
    assert request.url.host == "login.microsoftonline.com"
    assert request.url.path == TOKEN_PATH
    form = parse_qs(request.content.decode("utf-8"))
    assert form == {
        "client_id": [CLIENT_ID],
        "client_secret": ["test-client-secret"],
        "grant_type": [OBO_GRANT_TYPE],
        "assertion": ["api-access-token"],
        "requested_token_use": ["on_behalf_of"],
        "scope": [GRAPH_SCOPE],
    }
    return httpx.Response(200, json={"access_token": "delegated-graph-token"})


async def test_graph_adapter_resolves_minimal_profile_and_paginated_groups() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "login.microsoftonline.com":
            return token_response(request)
        assert request.headers["Authorization"] == "Bearer delegated-graph-token"
        if str(request.url).startswith(GRAPH_ME_URL + "?"):
            assert request.url.params["$select"] == PROFILE_SELECT
            return httpx.Response(
                200,
                json={
                    "id": USER_ID.upper(),
                    "displayName": "  Usuária de Segurança  ",
                    "mail": "security@example.com",
                    "userPrincipalName": "security@tenant.example.com",
                    "department": " Segurança da Informação ",
                    "userType": "Member",
                },
            )
        if request.url.params.get("$skiptoken") == "next-page":
            assert request.headers["ConsistencyLevel"] == "eventual"
            return httpx.Response(200, json={"value": [{"id": GROUP_TWO}]})
        assert str(request.url).startswith(GRAPH_GROUPS_URL + "?")
        assert request.url.params["$select"] == "id"
        assert request.url.params["$count"] == "true"
        assert request.url.params["$top"] == "999"
        assert request.headers["ConsistencyLevel"] == "eventual"
        return httpx.Response(
            200,
            json={
                "value": [{"id": GROUP_ONE}, {"id": GROUP_ONE}],
                "@odata.nextLink": f"{GRAPH_GROUPS_URL}?$skiptoken=next-page",
            },
        )

    profile = await directory(handler).resolve("api-access-token", expected_identity())

    assert len(requests) == 4
    assert profile.tenant_id == TENANT_ID
    assert profile.object_id == USER_ID
    assert profile.display_name == "Usuária de Segurança"
    assert profile.email_or_upn == "security@example.com"
    assert profile.department == "Segurança da Informação"
    assert profile.user_type == "Member"
    assert profile.group_object_ids == frozenset({GROUP_ONE, GROUP_TWO})


async def test_graph_adapter_rejects_untrusted_pagination_destination() -> None:
    requested_hosts: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        if request.url.host == "login.microsoftonline.com":
            return token_response(request)
        if request.url.path == "/v1.0/me":
            return httpx.Response(200, json={"id": USER_ID})
        return httpx.Response(
            200,
            json={
                "value": [{"id": GROUP_ONE}],
                "@odata.nextLink": "https://attacker.example.com/collect",
            },
        )

    with pytest.raises(CorporateDirectoryResponseInvalid, match="not trusted"):
        await directory(handler).resolve("api-access-token", expected_identity())

    assert "attacker.example.com" not in requested_hosts


async def test_graph_adapter_bounds_numeric_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return token_response(request)
        return httpx.Response(429, headers={"Retry-After": "600"})

    with pytest.raises(CorporateDirectoryUnavailable) as caught:
        await directory(handler, max_retry_after_seconds=90).resolve(
            "api-access-token",
            expected_identity(),
        )

    assert caught.value.retry_after_seconds == 90


async def test_graph_adapter_rejects_invalid_group_identifier() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return token_response(request)
        if request.url.path == "/v1.0/me":
            return httpx.Response(200, json={"id": USER_ID})
        return httpx.Response(200, json={"value": [{"id": "not-a-uuid"}]})

    with pytest.raises(CorporateDirectoryResponseInvalid, match="Graph id is invalid"):
        await directory(handler).resolve("api-access-token", expected_identity())


async def test_graph_adapter_rejects_pagination_beyond_local_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return token_response(request)
        if request.url.path == "/v1.0/me":
            return httpx.Response(200, json={"id": USER_ID})
        return httpx.Response(
            200,
            json={
                "value": [{"id": GROUP_ONE}],
                "@odata.nextLink": f"{GRAPH_GROUPS_URL}?$skiptoken=never-ending",
            },
        )

    with pytest.raises(CorporateDirectoryResponseInvalid, match="exceeded"):
        await directory(handler, max_pages=1).resolve(
            "api-access-token",
            expected_identity(),
        )


async def test_graph_adapter_rejects_object_mismatch_before_group_lookup() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.host == "login.microsoftonline.com":
            return token_response(request)
        return httpx.Response(
            200,
            json={"id": "66666666-6666-4666-8666-666666666666"},
        )

    with pytest.raises(CorporateDirectoryResponseInvalid, match="object ID"):
        await directory(handler).resolve("api-access-token", expected_identity())

    assert "/v1.0/me/transitiveMemberOf/microsoft.graph.group" not in requested_paths


async def test_graph_adapter_rejects_oversized_dependency_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            return token_response(request)
        return httpx.Response(200, content=b"{" + b"x" * (1024 * 1024) + b"}")

    with pytest.raises(CorporateDirectoryResponseInvalid, match="size limit"):
        await directory(handler).resolve("api-access-token", expected_identity())

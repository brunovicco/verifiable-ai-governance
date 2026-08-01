"""Microsoft Graph adapter using OAuth 2.0 On-Behalf-Of delegation."""

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx

from ai_governance_api.application.corporate_directory import (
    CorporateDirectoryProfile,
    CorporateDirectoryResponseInvalid,
    CorporateDirectoryUnavailable,
)
from ai_governance_api.domain.identity import DirectoryIdentity

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_ME_URL = f"{GRAPH_BASE_URL}/me"
GRAPH_GROUPS_URL = f"{GRAPH_ME_URL}/transitiveMemberOf/microsoft.graph.group"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
OBO_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"
PROFILE_SELECT = "id,displayName,mail,userPrincipalName,department,userType"
GROUPS_PATH_PREFIX = "/v1.0/me/transitiveMemberOf/microsoft.graph.group"


class MicrosoftGraphCorporateDirectory:
    """Resolve a minimal profile and transitive groups through delegated Graph access."""

    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        timeout_seconds: float,
        max_pages: int,
        max_retry_after_seconds: int,
        max_response_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize fixed Microsoft endpoints and bounded network behavior."""
        self._tenant_id = _canonical_uuid(tenant_id, field="tenant ID")
        self._client_id = _canonical_uuid(client_id, field="client ID")
        if not client_secret:
            raise ValueError("Microsoft Graph client secret must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("Microsoft Graph timeout must be positive")
        if max_pages < 1:
            raise ValueError("Microsoft Graph max pages must be positive")
        if max_retry_after_seconds < 0:
            raise ValueError("Microsoft Graph retry bound must not be negative")
        if max_response_bytes < 1:
            raise ValueError("Microsoft Graph response limit must be positive")
        self._client_secret = client_secret
        self._timeout_seconds = timeout_seconds
        self._max_pages = max_pages
        self._max_retry_after_seconds = max_retry_after_seconds
        self._max_response_bytes = max_response_bytes
        self._transport = transport
        self._token_url = (
            f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
        )

    async def resolve(
        self,
        user_assertion: str,
        expected_identity: DirectoryIdentity,
    ) -> CorporateDirectoryProfile:
        """Exchange the API token and fetch only the required directory attributes."""
        if not user_assertion.strip():
            raise CorporateDirectoryUnavailable()
        expected_tenant_id = _canonical_uuid(
            expected_identity.tenant_id,
            field="expected tenant ID",
        )
        expected_object_id = _canonical_uuid(
            expected_identity.object_id,
            field="expected object ID",
        )
        if expected_tenant_id != self._tenant_id:
            raise CorporateDirectoryResponseInvalid(
                "Authenticated tenant does not match the Graph adapter tenant"
            )
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                graph_token = await self._exchange_token(client, user_assertion)
                profile = await self._get_profile(client, graph_token)
                object_id = _required_uuid(profile, "id")
                if object_id != expected_object_id:
                    raise CorporateDirectoryResponseInvalid(
                        "Graph profile does not match the authenticated object ID"
                    )
                group_object_ids = await self._get_group_object_ids(client, graph_token)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise CorporateDirectoryUnavailable() from exc

        return CorporateDirectoryProfile(
            tenant_id=self._tenant_id,
            object_id=object_id,
            display_name=_optional_string(profile, "displayName"),
            email_or_upn=(
                _optional_string(profile, "mail")
                or _optional_string(profile, "userPrincipalName")
            ),
            department=_optional_string(profile, "department"),
            user_type=_optional_string(profile, "userType"),
            group_object_ids=group_object_ids,
        )

    async def _exchange_token(
        self,
        client: httpx.AsyncClient,
        user_assertion: str,
    ) -> str:
        """Exchange the API access token for a delegated Microsoft Graph token."""
        body = await self._request_json(
            client,
            "POST",
            self._token_url,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": OBO_GRANT_TYPE,
                "assertion": user_assertion,
                "requested_token_use": "on_behalf_of",
                "scope": GRAPH_SCOPE,
            },
            headers={"Accept": "application/json"},
        )
        access_token = body.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise CorporateDirectoryResponseInvalid("OBO response has no access token")
        return access_token

    async def _get_profile(
        self,
        client: httpx.AsyncClient,
        graph_token: str,
    ) -> Mapping[str, Any]:
        """Fetch the current user with an explicit minimal property selection."""
        return await self._request_json(
            client,
            "GET",
            GRAPH_ME_URL,
            params={"$select": PROFILE_SELECT},
            headers=self._graph_headers(graph_token),
        )

    async def _get_group_object_ids(
        self,
        client: httpx.AsyncClient,
        graph_token: str,
    ) -> frozenset[str]:
        """Fetch all transitive group object IDs with bounded trusted pagination."""
        url = GRAPH_GROUPS_URL
        params: Mapping[str, str] | None = {
            "$select": "id",
            "$count": "true",
            "$top": "999",
        }
        object_ids: set[str] = set()

        for _ in range(self._max_pages):
            body = await self._request_json(
                client,
                "GET",
                url,
                params=params,
                headers=self._graph_headers(graph_token, consistency_level="eventual"),
            )
            values = body.get("value")
            if not isinstance(values, list):
                raise CorporateDirectoryResponseInvalid("Graph groups response has no value list")
            for value in values:
                if not isinstance(value, Mapping):
                    raise CorporateDirectoryResponseInvalid(
                        "Graph groups response contains an invalid item"
                    )
                object_ids.add(_required_uuid(value, "id"))

            next_link = body.get("@odata.nextLink")
            if next_link is None:
                return frozenset(object_ids)
            url = _trusted_groups_next_link(next_link)
            params = None

        raise CorporateDirectoryResponseInvalid("Graph groups pagination exceeded its limit")

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        """Read a bounded successful JSON object without exposing remote content."""
        async with client.stream(
            method,
            url,
            data=data,
            params=params,
            headers=headers,
        ) as response:
            if response.status_code == 429:
                raise CorporateDirectoryUnavailable(
                    retry_after_seconds=self._retry_after_seconds(response)
                )
            if response.status_code < 200 or response.status_code >= 300:
                raise CorporateDirectoryUnavailable()

            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > self._max_response_bytes:
                    raise CorporateDirectoryResponseInvalid(
                        "Corporate directory response exceeds its size limit"
                    )
        try:
            body = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CorporateDirectoryResponseInvalid(
                "Corporate directory returned invalid JSON"
            ) from exc
        if not isinstance(body, Mapping):
            raise CorporateDirectoryResponseInvalid(
                "Corporate directory response must be an object"
            )
        return body

    def _retry_after_seconds(self, response: httpx.Response) -> int | None:
        """Return a non-negative numeric Retry-After bounded by local policy."""
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            seconds = int(value)
        except ValueError:
            return None
        return min(max(seconds, 0), self._max_retry_after_seconds)

    @staticmethod
    def _graph_headers(
        graph_token: str,
        *,
        consistency_level: str | None = None,
    ) -> dict[str, str]:
        """Build Graph headers without retaining the delegated token in domain data."""
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {graph_token}",
        }
        if consistency_level is not None:
            headers["ConsistencyLevel"] = consistency_level
        return headers


def _canonical_uuid(value: str, *, field: str) -> str:
    """Return a canonical non-nil UUID used by Microsoft identity contracts."""
    try:
        parsed = UUID(value.strip())
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Microsoft Graph {field} must be a UUID") from exc
    if parsed.int == 0:
        raise ValueError(f"Microsoft Graph {field} must be non-nil")
    return str(parsed)


def _required_uuid(body: Mapping[str, Any], field: str) -> str:
    """Read a required canonical non-nil UUID from a Graph object."""
    value = body.get(field)
    if not isinstance(value, str):
        raise CorporateDirectoryResponseInvalid(f"Graph {field} is missing")
    try:
        return _canonical_uuid(value, field=field)
    except ValueError as exc:
        raise CorporateDirectoryResponseInvalid(f"Graph {field} is invalid") from exc


def _optional_string(body: Mapping[str, Any], field: str) -> str | None:
    """Read and normalize an optional bounded textual Graph property."""
    value = body.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise CorporateDirectoryResponseInvalid(f"Graph {field} is invalid")
    normalized = value.strip()
    if len(normalized) > 512:
        raise CorporateDirectoryResponseInvalid(f"Graph {field} exceeds its size limit")
    return normalized or None


def _trusted_groups_next_link(value: object) -> str:
    """Accept pagination only on the fixed Microsoft Graph collection endpoint."""
    if not isinstance(value, str):
        raise CorporateDirectoryResponseInvalid("Graph nextLink is invalid")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "graph.microsoft.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.path != GROUPS_PATH_PREFIX
    ):
        raise CorporateDirectoryResponseInvalid("Graph nextLink is not trusted")
    return value

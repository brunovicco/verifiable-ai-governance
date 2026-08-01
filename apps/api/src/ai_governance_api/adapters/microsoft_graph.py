"""Microsoft Graph adapter using OAuth 2.0 On-Behalf-Of delegation."""

import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable, Mapping
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
RETRYABLE_GRAPH_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

logger = logging.getLogger(__name__)


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
        max_attempts: int,
        backoff_base_seconds: float,
        max_retry_delay_seconds: float,
        max_retry_after_seconds: int,
        max_response_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
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
        if max_attempts < 1:
            raise ValueError("Microsoft Graph max attempts must be positive")
        if backoff_base_seconds <= 0:
            raise ValueError("Microsoft Graph backoff base must be positive")
        if max_retry_delay_seconds <= 0:
            raise ValueError("Microsoft Graph retry delay bound must be positive")
        if max_retry_after_seconds < 0:
            raise ValueError("Microsoft Graph retry bound must not be negative")
        if max_response_bytes < 1:
            raise ValueError("Microsoft Graph response limit must be positive")
        self._client_secret = client_secret
        self._timeout_seconds = timeout_seconds
        self._max_pages = max_pages
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds
        self._max_retry_delay_seconds = max_retry_delay_seconds
        self._max_retry_after_seconds = max_retry_after_seconds
        self._max_response_bytes = max_response_bytes
        self._transport = transport
        self._sleep = sleep
        self._jitter = jitter
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
            operation="obo_token",
            retryable=False,
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
            operation="profile",
            retryable=True,
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
                operation="groups",
                retryable=True,
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
        operation: str,
        retryable: bool,
    ) -> Mapping[str, Any]:
        """Read bounded JSON and retry only explicitly safe transient operations."""
        for attempt in range(1, self._max_attempts + 1):
            try:
                async with client.stream(
                    method,
                    url,
                    data=data,
                    params=params,
                    headers=headers,
                ) as response:
                    if 200 <= response.status_code < 300:
                        return await self._read_json_object(response)
                    status_code = response.status_code
                    retry_after_hint_seconds = self._numeric_retry_after_seconds(
                        response
                    )
                    retry_after_seconds = self._bounded_retry_after_seconds(
                        retry_after_hint_seconds
                    )
            except (httpx.TimeoutException, httpx.TransportError):
                if not retryable or attempt >= self._max_attempts:
                    raise
                transport_delay_seconds = self._fallback_retry_delay(attempt)
                self._log_retry(
                    operation=operation,
                    status="transport_error",
                    attempt=attempt,
                    delay_seconds=transport_delay_seconds,
                )
                await self._sleep(transport_delay_seconds)
                continue

            if not retryable or status_code not in RETRYABLE_GRAPH_STATUS_CODES:
                raise CorporateDirectoryUnavailable(
                    retry_after_seconds=retry_after_seconds
                )
            if attempt >= self._max_attempts:
                self._log_retry_exhausted(
                    operation=operation,
                    status=str(status_code),
                    attempts=attempt,
                )
                raise CorporateDirectoryUnavailable(
                    retry_after_seconds=retry_after_seconds
                )

            response_delay_seconds = self._retry_delay(
                attempt,
                retry_after_hint_seconds,
            )
            if response_delay_seconds is None:
                logger.warning(
                    "microsoft_graph_retry_deferred operation=%s status=%s "
                    "attempt=%d retry_after_seconds=%s",
                    operation,
                    status_code,
                    attempt,
                    retry_after_seconds,
                )
                raise CorporateDirectoryUnavailable(
                    retry_after_seconds=retry_after_seconds
                )
            self._log_retry(
                operation=operation,
                status=str(status_code),
                attempt=attempt,
                delay_seconds=response_delay_seconds,
            )
            await self._sleep(response_delay_seconds)

        raise CorporateDirectoryUnavailable()

    async def _read_json_object(
        self,
        response: httpx.Response,
    ) -> Mapping[str, Any]:
        """Decode one bounded successful response without retaining its content."""
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

    def _retry_delay(
        self,
        attempt: int,
        retry_after_seconds: int | None,
    ) -> float | None:
        """Return an allowed server-directed or exponential retry delay."""
        if retry_after_seconds is not None:
            if retry_after_seconds > self._max_retry_delay_seconds:
                return None
            return float(retry_after_seconds)
        return self._fallback_retry_delay(attempt)

    def _fallback_retry_delay(self, attempt: int) -> float:
        """Return bounded exponential backoff with full base-interval jitter."""
        jitter = min(max(float(self._jitter()), 0.0), 1.0)
        exponential = self._backoff_base_seconds * (2 ** (attempt - 1))
        delay = min(
            exponential + (self._backoff_base_seconds * jitter),
            self._max_retry_delay_seconds,
        )
        return float(delay)

    def _log_retry(
        self,
        *,
        operation: str,
        status: str,
        attempt: int,
        delay_seconds: float,
    ) -> None:
        """Emit content-free retry telemetry for operational monitoring."""
        logger.warning(
            "microsoft_graph_retry operation=%s status=%s attempt=%d "
            "max_attempts=%d delay_seconds=%.3f",
            operation,
            status,
            attempt,
            self._max_attempts,
            delay_seconds,
        )

    @staticmethod
    def _log_retry_exhausted(
        *,
        operation: str,
        status: str,
        attempts: int,
    ) -> None:
        """Emit a content-free event when retry policy is exhausted."""
        logger.error(
            "microsoft_graph_retry_exhausted operation=%s status=%s attempts=%d",
            operation,
            status,
            attempts,
        )

    @staticmethod
    def _numeric_retry_after_seconds(response: httpx.Response) -> int | None:
        """Return a non-negative numeric Retry-After without trusting other formats."""
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            seconds = int(value)
        except ValueError:
            return None
        return max(seconds, 0)

    def _bounded_retry_after_seconds(self, seconds: int | None) -> int | None:
        """Bound the server hint before exposing it to an upstream caller."""
        if seconds is None or self._max_retry_after_seconds == 0:
            return None
        return min(seconds, self._max_retry_after_seconds)

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

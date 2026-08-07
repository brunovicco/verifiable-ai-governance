"""Bounded HTTP adapter for the policy-model-router decision contract."""

import json
from datetime import datetime, timedelta
from typing import Annotated, Literal

import httpx
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
)

from ai_governance_api.application.model_routing import ModelRouterUnavailable
from ai_governance_api.domain.model_routing import (
    PolicyModelRouterDecision,
    PolicyModelRouterRequest,
    RejectedRoutingCandidate,
    RouterDecisionOutcome,
    RoutingWorkload,
)

_Identifier = Annotated[str, StringConstraints(min_length=1, max_length=200)]
_Description = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
_ConstraintValue = Annotated[str, StringConstraints(min_length=1, max_length=1000)]
_ModelGroup = Annotated[
    str,
    StringConstraints(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$"),
]
_ReasonCode = Annotated[
    str,
    StringConstraints(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_]*$"),
]
_Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def _require_utc(value: datetime) -> datetime:
    """Reject timestamps that are naive or not expressed in UTC."""
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be expressed in UTC")
    return value


UtcDatetime = Annotated[datetime, AfterValidator(_require_utc)]


class _StrictContract(BaseModel):
    """Closed external contract used only inside the HTTP adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class _RejectedCandidateContract(_StrictContract):
    """Validated rejected-candidate wire representation."""

    model_group: _ModelGroup
    reason: _Description
    reason_code: _ReasonCode
    observed_value: _ConstraintValue
    required_value: _ConstraintValue


class _AcceptedDecisionContract(_StrictContract):
    """Validated accepted policy-model-router response."""

    schema_version: Literal["1.0"]
    routing_decision_id: _Identifier
    decided_at: UtcDatetime
    workflow_id: _Identifier
    task_id: _Identifier
    selected_model_group: _ModelGroup
    reason: _Description
    rejected_candidates: tuple[_RejectedCandidateContract, ...] = Field(max_length=100)
    policy_id: _Identifier
    policy_version: _Identifier
    policy_digest: _Digest
    service_version: _Identifier
    environment: _Identifier


class _RejectedDecisionContract(_StrictContract):
    """Validated hard-rejection decision embedded in a 422 response."""

    schema_version: Literal["1.0"]
    routing_decision_id: _Identifier
    decided_at: UtcDatetime
    workflow_id: _Identifier
    task_id: _Identifier
    workload: RoutingWorkload
    rejected_model_group: _ModelGroup
    reason: _Description
    reason_code: _ReasonCode
    observed_value: _ConstraintValue
    required_value: _ConstraintValue
    policy_id: _Identifier
    policy_version: _Identifier
    policy_digest: _Digest
    service_version: _Identifier
    environment: _Identifier


class _ErrorContract(_StrictContract):
    """Stable policy-model-router error envelope entry."""

    code: _ReasonCode
    message: _Description


class _RejectedEnvelopeContract(_StrictContract):
    """Stable envelope for one auditable hard routing rejection."""

    error: _ErrorContract
    decision: _RejectedDecisionContract


class PolicyModelRouterHttpAdapter:
    """Call policy-model-router once with per-agent credentials and strict bounds."""

    def __init__(
        self,
        *,
        base_url: str,
        api_keys: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize immutable deployment configuration and optional test transport."""
        self._route_url = f"{base_url.rstrip('/')}/route"
        self._api_keys = dict(api_keys)
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_response_bytes = max_response_bytes
        self._transport = transport

    async def decide(
        self,
        request: PolicyModelRouterRequest,
        *,
        correlation_id: str,
    ) -> PolicyModelRouterDecision:
        """Obtain one decision without retrying the non-idempotent POST operation."""
        api_key = self._api_keys.get(request.agent_name)
        if api_key is None:
            raise ModelRouterUnavailable("No routing credential configured for governed agent")
        try:
            async with (
                httpx.AsyncClient(
                    timeout=self._timeout,
                    transport=self._transport,
                ) as client,
                client.stream(
                    "POST",
                    self._route_url,
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": api_key,
                        "X-Correlation-Id": correlation_id,
                    },
                    json=_request_payload(request),
                ) as response,
            ):
                body = await self._read_bounded(response)
                status_code = response.status_code
        except httpx.HTTPError as exc:
            raise ModelRouterUnavailable("Policy model router request failed") from exc

        try:
            payload = json.loads(body)
            if status_code == 200:
                decision = _accepted_to_domain(_AcceptedDecisionContract.model_validate(payload))
                _require_request_binding(request, decision)
                return decision
            if status_code == 422:
                envelope = _RejectedEnvelopeContract.model_validate(payload)
                if envelope.error.code != "no_viable_model_group":
                    raise ModelRouterUnavailable(
                        "Policy model router rejected the adapter contract"
                    )
                if envelope.decision.workload is not request.workload:
                    raise ModelRouterUnavailable(
                        "Policy model router rejection does not match the request"
                    )
                decision = _rejected_to_domain(envelope.decision)
                _require_request_binding(request, decision)
                return decision
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise ModelRouterUnavailable("Policy model router response is invalid") from exc
        raise ModelRouterUnavailable(
            f"Policy model router returned unavailable status {status_code}"
        )

    async def _read_bounded(self, response: httpx.Response) -> bytes:
        """Read a response under an explicit memory and parser boundary."""
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self._max_response_bytes:
                    raise ModelRouterUnavailable("Policy model router response is too large")
            except ValueError as exc:
                raise ModelRouterUnavailable(
                    "Policy model router Content-Length is invalid"
                ) from exc
        chunks: list[bytes] = []
        received = 0
        async for chunk in response.aiter_bytes():
            received += len(chunk)
            if received > self._max_response_bytes:
                raise ModelRouterUnavailable("Policy model router response is too large")
            chunks.append(chunk)
        return b"".join(chunks)


def _request_payload(request: PolicyModelRouterRequest) -> dict[str, object]:
    """Serialize the exact versioned request without prompt or document content."""
    return {
        "schema_version": request.schema_version,
        "requested_at": request.requested_at.isoformat(),
        "workflow_id": request.workflow_id,
        "task_id": request.task_id,
        "agent_name": request.agent_name,
        "workload": request.workload.value,
        "risk_level": request.risk_level.value,
        "data_classification": request.data_classification.value,
        "context_tokens_estimated": request.context_tokens_estimated,
        "max_output_tokens_estimated": request.max_output_tokens_estimated,
        "structured_output_required": request.structured_output_required,
        "max_latency_ms": request.max_latency_ms,
        "max_cost_usd": str(request.max_cost_usd),
    }


def _require_request_binding(
    request: PolicyModelRouterRequest,
    decision: PolicyModelRouterDecision,
) -> None:
    """Reject a valid-shaped decision that belongs to a different operation."""
    if (
        decision.schema_version != request.schema_version
        or decision.workflow_id != request.workflow_id
        or decision.task_id != request.task_id
    ):
        raise ModelRouterUnavailable("Policy model router decision does not match the request")


def _accepted_to_domain(contract: _AcceptedDecisionContract) -> PolicyModelRouterDecision:
    """Map a trusted accepted response into framework-independent types."""
    return PolicyModelRouterDecision(
        outcome=RouterDecisionOutcome.ACCEPTED,
        schema_version=contract.schema_version,
        routing_decision_id=contract.routing_decision_id,
        decided_at=contract.decided_at,
        workflow_id=contract.workflow_id,
        task_id=contract.task_id,
        selected_model_group=contract.selected_model_group,
        rejected_model_group=None,
        reason=contract.reason,
        reason_code=None,
        observed_value=None,
        required_value=None,
        rejected_candidates=tuple(
            RejectedRoutingCandidate(
                model_group=item.model_group,
                reason=item.reason,
                reason_code=item.reason_code,
                observed_value=item.observed_value,
                required_value=item.required_value,
            )
            for item in contract.rejected_candidates
        ),
        policy_id=contract.policy_id,
        policy_version=contract.policy_version,
        policy_digest=contract.policy_digest,
        service_version=contract.service_version,
        environment=contract.environment,
    )


def _rejected_to_domain(contract: _RejectedDecisionContract) -> PolicyModelRouterDecision:
    """Map a trusted hard rejection into the shared provider-decision type."""
    return PolicyModelRouterDecision(
        outcome=RouterDecisionOutcome.REJECTED,
        schema_version=contract.schema_version,
        routing_decision_id=contract.routing_decision_id,
        decided_at=contract.decided_at,
        workflow_id=contract.workflow_id,
        task_id=contract.task_id,
        selected_model_group=None,
        rejected_model_group=contract.rejected_model_group,
        reason=contract.reason,
        reason_code=contract.reason_code,
        observed_value=contract.observed_value,
        required_value=contract.required_value,
        rejected_candidates=(),
        policy_id=contract.policy_id,
        policy_version=contract.policy_version,
        policy_digest=contract.policy_digest,
        service_version=contract.service_version,
        environment=contract.environment,
    )

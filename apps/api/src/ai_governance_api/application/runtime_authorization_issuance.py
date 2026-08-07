"""Build signed runtime authorization from fresh governed routing scope."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from governance_schemas import (
    AuthorizedRuntimeModel,
    DataClassification,
    EntityStatus,
    RuntimeAuthorizationClaims,
    RuntimeAuthorizationPolicyProvenance,
    RuntimeAuthorizationScope,
    RuntimeAuthorizationSubject,
    RuntimeRequestBinding,
    SignedRuntimeAuthorization,
)

from ai_governance_api.application.runtime_authorization_security import (
    RuntimeAuthorizationSigner,
)
from ai_governance_api.domain.asset_registry import review_is_current
from ai_governance_api.domain.model_routing import (
    GovernedRoutingScope,
    ModelRoutingCommand,
    evaluate_routing_scope,
)


class RuntimeAuthorizationIssuanceError(RuntimeError):
    """Raised when Governance cannot safely authorize one runtime request."""


@dataclass(frozen=True, slots=True)
class RuntimeAuthorizationIssuancePolicy:
    """Immutable deployment provenance embedded in every authorization."""

    issuer: str
    audience: tuple[str, ...]
    lifetime_seconds: int
    policy_id: str
    policy_version: str
    policy_digest: str
    control_catalog_id: str
    control_catalog_version: str
    control_catalog_digest: str


class GovernanceRuntimeAuthorizationIssuer:
    """Convert current governed scope into one request-scoped signed artifact."""

    def __init__(
        self,
        signer: RuntimeAuthorizationSigner,
        policy: RuntimeAuthorizationIssuancePolicy,
    ) -> None:
        """Bind the signer to immutable Governance provenance."""
        if not 1 <= policy.lifetime_seconds <= 600:
            raise ValueError("Runtime authorization lifetime must be between 1 and 600 seconds")
        if "policy-model-router" not in policy.audience:
            raise ValueError("Runtime authorization must include policy-model-router audience")
        self._signer = signer
        self._policy = policy

    def issue(
        self,
        scope: GovernedRoutingScope,
        command: ModelRoutingCommand,
        *,
        authorization_id: str,
        issued_at: datetime,
    ) -> SignedRuntimeAuthorization:
        """Issue one artifact only while the supplied scope remains runtime-eligible."""
        block = evaluate_routing_scope(scope, command, now=issued_at)
        if block is not None:
            raise RuntimeAuthorizationIssuanceError(
                f"Governed scope is not authorizable: {block.code}"
            )
        if scope.agent_approved_scope_digest is None:
            raise RuntimeAuthorizationIssuanceError("Agent approved-scope digest is required")
        if scope.agent_max_runtime_seconds is None:
            raise RuntimeAuthorizationIssuanceError(
                "Agent runtime limit is required for signed authorization"
            )
        if not scope.agent_kill_switch_enabled:
            raise RuntimeAuthorizationIssuanceError(
                "Agent kill switch must be enabled for signed authorization"
            )

        models = self._authorized_models(scope, issued_at)
        if not models:
            raise RuntimeAuthorizationIssuanceError(
                "No reviewed model can be encoded in signed authorization"
            )

        try:
            claims = RuntimeAuthorizationClaims(
                authorization_id=authorization_id,
                issuer=self._policy.issuer,
                audience=self._policy.audience,
                issued_at=issued_at,
                not_before=issued_at,
                expires_at=issued_at + timedelta(seconds=self._policy.lifetime_seconds),
                subject=RuntimeAuthorizationSubject(
                    initiative_id=scope.initiative_id,
                    ai_system_id=scope.ai_system_id,
                    ai_system_version=scope.ai_system_version,
                    agent_id=scope.agent_id,
                    agent_version=scope.agent_version,
                    agent_review_digest=scope.agent_approved_scope_digest,
                ),
                request=RuntimeRequestBinding(
                    workflow_id=command.workflow_id,
                    task_id=command.task_id,
                    workload=command.workload.value,
                    context_tokens_estimated=command.context_tokens_estimated,
                    max_output_tokens_estimated=command.max_output_tokens_estimated,
                    structured_output_required=command.structured_output_required,
                    max_latency_ms=command.max_latency_ms,
                    max_cost_usd_micros=_usd_micros(command.max_cost_usd),
                ),
                scope=RuntimeAuthorizationScope(
                    risk_tier=scope.risk_tier,
                    data_classification=scope.data_classification,
                    autonomy_level=scope.agent_autonomy_level,
                    models=models,
                    allowed_tools=scope.agent_tools,
                    permissions=scope.agent_permissions,
                    max_runtime_seconds=scope.agent_max_runtime_seconds,
                    human_approval_points=scope.agent_human_approval_points,
                    kill_switch_enabled=True,
                ),
                scope_digest=scope.digest,
                policy=RuntimeAuthorizationPolicyProvenance(
                    policy_id=self._policy.policy_id,
                    policy_version=self._policy.policy_version,
                    policy_digest=self._policy.policy_digest,
                    control_catalog_id=self._policy.control_catalog_id,
                    control_catalog_version=self._policy.control_catalog_version,
                    control_catalog_digest=self._policy.control_catalog_digest,
                ),
            )
            return self._signer.sign(claims)
        except RuntimeAuthorizationIssuanceError:
            raise
        except ValueError as exc:
            raise RuntimeAuthorizationIssuanceError(
                "Runtime authorization contract or signature could not be trusted"
            ) from exc

    @staticmethod
    def _authorized_models(
        scope: GovernedRoutingScope,
        now: datetime,
    ) -> tuple[AuthorizedRuntimeModel, ...]:
        """Return current reviewed, data-compatible models explicitly allowed by the agent."""
        allowed_ids = set(scope.agent_allowed_model_ids)
        models: list[AuthorizedRuntimeModel] = []
        for model in scope.models:
            if (
                model.id not in allowed_ids
                or model.status is not EntityStatus.APPROVED
                or not model.scope_digest_matches
                or model.approved_scope_digest is None
                or not model.routing_group.strip()
                or model.routing_group == "unassigned"
                or not review_is_current(next_review_at=model.next_review_at, now=now)
                or scope.data_classification.value not in model.allowed_data_classes
            ):
                continue
            try:
                data_classes = tuple(
                    DataClassification(value) for value in model.allowed_data_classes
                )
            except ValueError as exc:
                raise RuntimeAuthorizationIssuanceError(
                    "Model contains an unsupported data classification"
                ) from exc
            models.append(
                AuthorizedRuntimeModel(
                    model_id=model.id,
                    entity_version=model.version,
                    model_version=model.model_version,
                    routing_group=model.routing_group,
                    review_digest=model.approved_scope_digest,
                    allowed_data_classes=data_classes,
                )
            )
        return tuple(models)


def _usd_micros(value: Decimal) -> int:
    """Convert exact decimal USD to integer micros without rounding."""
    micros = value * Decimal(1_000_000)
    integral = micros.to_integral_value()
    if micros != integral:
        raise RuntimeAuthorizationIssuanceError(
            "Requested cost cannot be represented as integer USD micros"
        )
    result = int(integral)
    if result < 0:
        raise RuntimeAuthorizationIssuanceError("Requested cost must not be negative")
    return result

# Runtime kill switch operations

P1.6a introduces an agent-scoped emergency stop that is durable in PostgreSQL, projected monotonically to Redis, and audited in the existing hash chain.

## Configuration

For Docker Compose, P1.6a enables the included Redis service by default. For staging/production deployments that enable policy-model-router, configure:

```bash
RUNTIME_CONTROL_ENABLED=true
RUNTIME_CONTROL_REDIS_URL=rediss://runtime-control-redis:6379/0
RUNTIME_CONTROL_REDIS_KEY_PREFIX=verifiable-ai-governance:runtime-control:v1:agent:
RUNTIME_CONTROL_REDIS_TIMEOUT_SECONDS=2
```

Staging/production configuration requires `rediss://`. Use separate least-privilege credentials where the Governance API can write and the later Router integration can be read-only. Never expose Redis publicly.

## Bootstrap before Router enforcement

Before enabling P1.6b strict Router enforcement, pre-project all existing Agent states:

```bash
uv run python -m ai_governance_api.runtime_control_bootstrap --batch-size 250
```

The command uses keyset pagination and the same issuance gate semantics. It may repair only missing or strictly older snapshots. A pending transition, unexplained newer epoch, same-epoch divergence, malformed document, or Redis outage aborts the bootstrap. Do not enable Router fail-closed reads until this command succeeds.

## Activate

```http
POST /api/v1/agents/{agent_id}/runtime-control/activate
Content-Type: application/json

{
  "expected_version": 17,
  "reason": "Emergency containment after runtime policy violation",
  "incident_id": "optional-incident-uuid",
  "evidence_reference": "optional-evidence-reference"
}
```

A successful response means the runtime projection was acknowledged and the Agent durable state was finalized. A 503 with `runtime_control_unavailable` means fail-closed behavior is preserved; inspect pending transitions and reconcile after dependency recovery.

## Deactivate

Use the same payload with:

```http
POST /api/v1/agents/{agent_id}/runtime-control/deactivate
```

Deactivation increments the Agent version. The projected `revoked_through_agent_version` remains at the pre-restore version, so authorizations signed before restore remain unusable when Router enforcement lands in P1.6b.

## Reconcile pending transitions

Administrators can repair transitions left pending by partial failures:

```http
POST /api/v1/runtime-control/reconcile
Content-Type: application/json

{"limit": 100}
```

Reconciliation is idempotent. It reprojects the exact transition snapshot and only then finalizes durable Agent state. Same-epoch conflicting Redis content is not overwritten and requires investigation.

## Failure semantics

- Redis unavailable before request: no transition is acknowledged; operation returns 503.
- DB transition committed but Redis unavailable: transition remains `pending`; authorization issuance fails closed until reconciliation.
- Redis applied but DB finalization fails: runtime remains safely stopped/restored according to the projected epoch, while Governance issuance fails closed because the durable transition is pending.
- Missing/older Redis snapshot during pre-issuance or post-Router enforcement: Governance may repair it only from unambiguous durable state.
- Newer/same-epoch divergent/malformed Redis state: fail closed; do not force overwrite.

## Evidence to capture during an incident

Record the `transition_id`, `control_epoch`, `agent_id`, `revoked_through_agent_version`, operator, reason, optional `incident_id`, and relevant runtime violation ID. Do not copy prompts, outputs, tokens, API keys, or Redis credentials into the audit reason/evidence reference.

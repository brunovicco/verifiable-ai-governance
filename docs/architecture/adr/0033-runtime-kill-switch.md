# ADR-0033: Monotonic runtime kill switch and authorization revocation floor

## Status

Accepted for P1.6a.

## Context

P1.1-P1.5 established reviewed runtime scope, short-lived Ed25519 authorization, Router enforcement, durable violation evidence, and distributed tracing. The existing `Agent` aggregate already declares and persists `kill_switch_enabled` and `kill_switch_engaged`, but that state was not projected to the runtime trust boundary. A signed authorization issued immediately before an emergency stop could therefore remain cryptographically valid until expiry.

## Decision

P1.6a keeps `Agent.kill_switch_engaged` as the durable effective state and adds appendable `RuntimeControlTransition` evidence. Each transition receives a monotonically increasing per-agent `control_epoch` and records `revoked_through_agent_version` equal to the optimistic Agent version observed when the transition is requested.

The shared runtime projection is a no-TTL Redis document keyed by agent ID. Writes use atomic compare-and-set semantics:

- newer epoch: apply;
- identical epoch and payload: idempotent success;
- older epoch: reject;
- same epoch with different payload: reject.

The already-signed `RuntimeAuthorizationSubject.agent_version` is deliberately reused as the revocation primitive. The authorization contract is not versioned or expanded in P1.6a. P1.6b will require the Router to deny when the runtime state is active or when `subject.agent_version <= revoked_through_agent_version`.

## Two-phase operational transition

1. Governance locks the Agent, creates a `pending` transition, appends audit evidence, and commits.
2. Governance projects the target snapshot to Redis.
3. Governance re-locks durable state, applies `kill_switch_engaged`, increments the Agent version, marks the transition `applied`, and appends final audit evidence.

A pending transition blocks trusted runtime authorization issuance. Governance also rechecks Runtime Control after an accepted Router call and before finalizing `ALLOWED`, closing the in-flight race where a transition can become pending after the pre-issuance check. If projection succeeds but DB finalization fails, runtime remains fail-safe and an administrator can reconcile the pending transition. If Redis is unavailable before step 1, no transition is acknowledged as requested.

## Recovery and bootstrap

The Governance issuance gate reads durable state using a short-lived DB session, then verifies the Redis snapshot. Missing or strictly older snapshots may be repaired from durable evidence. Pending transitions, same-epoch divergence, newer unexplained runtime epochs, malformed documents, and backend unavailability fail closed.

Local/test environments may use a process-local monotonic projection. Distributed environments with policy-model-router enabled require Redis-backed runtime control.

## Authorization and audit

Activation and deactivation require the AI-system owner, Agent owner, or administrator. Activation does not require a pre-existing Incident; incident and evidence references remain optional correlation fields. Legacy incident-bound endpoints delegate to the same Runtime Control service.

Audit actions are:

- `runtime_control.activation_requested`
- `runtime_control.activated`
- `runtime_control.deactivation_requested`
- `runtime_control.deactivated`
- `runtime_control.projection_reconciled`

Audit payloads contain only structural state, actor/reason references, epochs, versions, and optional incident/evidence identifiers. Prompts, outputs, credentials, and model content are excluded.

## Consequences

The design invalidates pre-stop authorizations without waiting for their TTL and prevents restore from resurrecting them. It avoids a breaking Runtime Authorization schema change and preserves the existing Agent aggregate as the single durable state owner. Redis becomes required infrastructure for distributed runtime enforcement and must be treated as fail-closed.

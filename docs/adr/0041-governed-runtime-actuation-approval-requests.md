# ADR 0041 — Governed Runtime Actuation Approval Requests

- Status: Accepted
- Date: 2026-08-09
- Scope: P1.9a

## Context

P1.8c emits deterministic, advisory-only `RuntimeAssuranceResponseRecommendation` evidence. A critical recommendation may contain `consider_kill_switch`, but P1.8 deliberately proves that recommendation is not actuation.

P1.9 introduces human-approved governed actuation. P1.9a establishes only the immutable intent/approval-request boundary. It must not invoke Runtime Control, mutate an Agent or Incident, or call the Policy Model Router.

## Decision

### Recommendation and actuation use different vocabularies

`consider_kill_switch` remains an advisory recommendation action. The governed actuation action is `engage_kill_switch`.

The distinction is intentional: recommendation evidence cannot be confused with an executable command. The HTTP client cannot submit an action. The server deterministically derives `engage_kill_switch` only when persisted trusted recommendation evidence contains `consider_kill_switch` and remains internally consistent.

### Explicit request resource

Actuation intent begins only through:

`POST /api/v1/runtime-assurance-response-recommendations/{recommendation_id}/actuation-request`

The request body is the closed object `{}`. Fields such as `force`, `agent_id`, `kill_switch`, `action`, expected versions, actuator configuration, or arbitrary metadata are rejected.

The matching GET is singular because P1.9a permits at most one request for the `(recommendation_id, action)` natural key.

### Immutable genesis evidence

`runtime_assurance_actuation_requests` stores the immutable genesis evidence for one governed request. P1.9a implements only the concrete state `pending`.

The row is not designed as a mutable workflow record. P1.9b must append approval/rejection evidence rather than overwrite the original requester, lineage, action, timestamp, or digest. Additional effective states may be introduced only together with concrete event semantics.

### Strong binding

Each request binds:

- request ID and schema version;
- recommendation ID and `recommendation_digest`;
- promotion ID;
- evaluation ID;
- incident ID;
- Agent ID;
- AI System ID;
- governed action;
- requester identity;
- request timestamp;
- version.

Foreign keys enforce structural references. The persistence adapter independently validates the recommendation → promotion → evaluation → incident → Agent → AI System lineage before request creation. It also re-derives the P1.8c plan with the existing deterministic response-policy primitive and requires the stored policy digest, actions, rationale codes, and `recommendation_digest` to match. P1.9a does not implement a parallel recommendation-digest algorithm. The canonical request digest binds the full immutable request representation.

This prevents cross-Agent and cross-recommendation reuse.

### Canonical digest

The request digest is SHA-256 over canonical JSON using sorted keys and compact separators. The digest includes all immutable binding fields, the distinct action `engage_kill_switch`, the `pending` state, the requester, and the UTC request timestamp.

A persisted request is revalidated against both its source context and a recomputed digest before idempotent replay or GET.

### Authorization and segregation of duties

P1.9a request creation is limited to the AI System owner or an administrator, matching the existing governed Runtime Assurance owner/admin boundary while intentionally excluding Agent-owner-only authority.

`requested_by` is immutable evidence. For the high-impact `engage_kill_switch` action, P1.9b should require an independent principal (`approver != requester`) and an explicit governance approval capability/area rather than reusing AI System ownership as approval authority. A generic administrator bypass should not silently defeat segregation of duties; any future break-glass path must be separately governed and evidenced. P1.9a records the requester needed for that enforcement but deliberately does not invent a generic approval role or approval-policy payload.

### Idempotency and concurrency

A unique constraint on `(recommendation_id, action)` is the durable idempotency key. Creation serializes under the existing AI System row lock used by Runtime Assurance response flows, then returns the existing, fully revalidated request when the same command is retried.

An idempotent replay does not append a second audit event.

### Audit evidence

Creation appends `runtime_assurance.actuation_requested` to the shared hash-chained audit log in the same database transaction as the request row.

The audit payload is intentionally minimized to:

- recommendation ID;
- Agent ID;
- AI System ID;
- governed action;
- request digest.

Recommendation rationale, telemetry bodies, prompts, model outputs, credentials, tokens, and arbitrary runtime payloads are excluded.

### Fail-closed behavior

Creation fails closed when:

- recommendation evidence does not exist;
- trusted lineage is inconsistent;
- recommendation is not advisory-only;
- `consider_kill_switch` is absent;
- kill-switch recommendation evidence is internally inconsistent;
- the current linked incident is closed for a new request;
- the caller is unauthorized;
- an existing request fails lineage or digest validation.

### TOCTOU boundary

P1.9a does not treat recommendation-time Runtime Control state as current authority and does not persist a new authoritative Runtime Control snapshot.

P1.9c must re-read and validate authoritative Runtime Control and Agent state immediately before execution. Approval means permission to attempt the bounded action, not proof that runtime preconditions still hold.

### Restore is a separate governed action

An approval to `engage_kill_switch` can never authorize restore. A future restore path requires a distinct recommendation/intention, request, approval evidence, digest, and execution command. No engage approval is reusable for restore.

### No LLM

No LLM participates in request creation, action derivation, authorization, binding validation, digest calculation, approval, or execution.

## Consequences

- P1.8c remains provably advisory-only.
- P1.9a introduces no Runtime Control dependency and therefore has no hidden actuation path.
- Human approval can be added in P1.9b without changing immutable request genesis evidence.
- P1.9c receives an explicit approved-request boundary and must still perform fresh TOCTOU checks before calling Runtime Control.
- The Policy Model Router remains downstream of Runtime Control only after a separately approved and executed P1.9c transition.

## Explicit non-goals for P1.9a

P1.9a does not:

- approve or reject requests;
- expire or cancel requests;
- execute Runtime Control;
- engage or restore the kill switch;
- mutate Agent or Incident state;
- create Runtime Control transitions;
- call the Policy Model Router;
- infer policy with an LLM;
- create a generic actuator/configuration payload;
- treat recommendation-time kill-switch state as current runtime truth.

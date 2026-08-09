# ADR 0042 — Governed Runtime Actuation Decisions

- Status: Accepted
- Date: 2026-08-09
- Scope: P1.9b

## Context

P1.9a introduced immutable `runtime_assurance_actuation_requests` as governed intent only.
A request binds trusted Runtime Assurance recommendation lineage to the concrete action
`engage_kill_switch`, but remains permanently recorded as genesis evidence with
`state = pending`.

P1.9b must add independent human approval or rejection without converting that genesis row
into a mutable workflow record and without executing Runtime Control.

## Decision

### Human decision is a distinct append-only resource

P1.9b introduces `RuntimeAssuranceActuationDecision` and the table
`runtime_assurance_actuation_decisions`.

Each decision is terminal and immutable. It binds:

- decision ID and schema version;
- actuation request ID;
- canonical P1.9a `request_digest`;
- concrete governed action;
- decision outcome;
- approval area;
- authenticated decision-maker identity;
- decision timestamp;
- normalized human reason;
- canonical `decision_digest`;
- evidence version.

The P1.9a actuation-request row is never updated. Its `pending` value describes the immutable
request genesis, not the effective workflow state after P1.9b.

### Closed decision vocabulary

P1.9b supports exactly:

- `approved`;
- `rejected`.

There is no cancellation, expiration, supersession, reconsideration, or break-glass state in
this phase.

### Explicit Security approval capability

`engage_kill_switch` is a high-impact containment action. P1.9b therefore requires the
existing governance capability `ApprovalArea.SECURITY` for both approval and rejection.

AI System ownership is not approval authority. `is_admin = true` alone is not approval
authority. An administrator may decide only when the authenticated principal also carries the
Security approval area.

This intentionally reuses the repository's existing approval-area taxonomy instead of adding a
P1.9b-only role model.

### Mandatory segregation of duties

The authenticated decision maker must differ from the immutable P1.9a requester:

`decided_by != requested_by`

This rule is absolute in P1.9b. Security capability, AI System ownership, or administrator
status does not bypass it.

A future emergency/break-glass mechanism, if needed, must have a separate governed contract,
reason, evidence, authorization policy, and audit semantics.

### Server-derived identity, action, and approval area

The API is:

`POST /api/v1/runtime-assurance-actuation-requests/{request_id}/decision`

The client supplies only:

```json
{
  "decision": "approved",
  "reason": "Reviewed by Security and approved for containment."
}
```

The authenticated principal supplies `decided_by`. The server derives the request, governed
action, request digest, lineage, and required approval area.

Fields such as `action`, `approver`, `agent_id`, `ai_system_id`, `force`, Runtime Control
configuration, expected Agent version, or actuator payload are rejected.

### Request lineage is revalidated

The decision persistence adapter loads the immutable P1.9a request and reuses the P1.9a trusted
recommendation-lineage repository. It then re-runs the existing P1.9a request-binding
validation.

P1.9b therefore does not create a second implementation of the P1.8c recommendation digest or
of the P1.9a request digest.

The decision is cryptographically rooted in `request_digest`, which already binds the
recommendation, promotion, evaluation, incident, Agent, AI System, action, requester, and
request timestamp.

### Canonical decision digest

`decision_digest` is SHA-256 over canonical JSON with sorted keys and compact separators.
It includes:

- schema version;
- decision ID;
- request ID;
- request digest;
- action;
- decision outcome;
- approval area;
- decision maker;
- UTC decision timestamp;
- normalized reason;
- version.

Changing the actor, reason, outcome, request, action, approval area, timestamp, or version
invalidates the evidence.

### Reason is mandatory and bounded

A decision reason is required, whitespace-trimmed, non-empty, and limited to 2,000 characters.
It is part of the canonical digest.

The full reason is stored only on the governed decision record. It is intentionally omitted
from the hash-chained audit payload to minimize duplicated sensitive content.

### Durable single-decision invariant

A unique constraint on `request_id` allows at most one terminal decision for an actuation
request.

Decision creation locks the immutable request row before checking for existing decision
evidence. The database unique constraint remains the durable concurrency backstop.

A retry is idempotent only when the existing evidence matches the same:

- authenticated decision maker;
- decision outcome;
- normalized reason;
- required approval area;
- trusted request binding.

A different outcome, different reason, or different actor returns conflict rather than
rewriting the existing evidence.

### Closed-incident semantics

A new `approved` decision fails closed when the linked incident is already `closed` at decision
time.

A `rejected` decision may still be recorded for a closed incident because rejection cannot
authorize runtime actuation and preserves the human governance outcome.

This decision-time incident check is not an execution precondition snapshot. P1.9c must still
perform fresh authoritative TOCTOU validation immediately before any runtime mutation.

### Audit evidence

A new decision appends one of:

- `runtime_assurance.actuation_approved`;
- `runtime_assurance.actuation_rejected`.

The audit payload is minimized to:

- request ID;
- Agent ID;
- AI System ID;
- governed action;
- approval area;
- decision digest.

The full reason is not duplicated into audit.

An idempotent replay does not create a second audit event.

### Read authorization

Decision evidence may be read by:

- the original requester;
- the AI System owner;
- a principal with Security approval capability;
- an administrator.

This visibility policy does not grant approval authority. Decision creation still requires
Security capability plus segregation of duties.

### Approval is not execution authority without P1.9c checks

`approved` means that an independent authorized human has approved an attempt to perform the
bounded action.

It does not mean:

- Runtime Control has changed;
- the Agent kill switch is engaged;
- the incident is still actionable;
- Agent version/preconditions are unchanged;
- the action may be replayed indefinitely.

P1.9c must consume the immutable approved decision, revalidate its full evidence chain, re-read
current authoritative Runtime Control and Agent state, enforce fresh preconditions, and only
then execute one bounded transition.

### No Runtime Control or Router dependency

P1.9b does not execute Runtime Control. The service and persistence adapter do not import or
invoke Runtime Control, Incident
kill-switch mutation, Policy Model Router, HTTP clients, or LLMs.

Boundary tests enforce this constraint.

## Consequences

- Recommendation, request, human decision, and execution remain distinct resources.
- P1.9a genesis evidence remains immutable.
- Security approval authority is explicit and testable.
- Generic administrator status cannot silently defeat approval policy.
- Segregation of duties is mechanically enforced.
- Human decision evidence is cryptographically bound to the P1.9a request.
- P1.9c can require a validated `approved` decision without trusting mutable workflow state.

## P1.9c boundary

P1.9c may implement execution only after validating all of the following:

1. the P1.9a request is valid and bound to trusted Runtime Assurance lineage;
2. the P1.9b decision is valid, `approved`, and bound to that exact request digest;
3. Security approval and segregation-of-duties evidence remain internally consistent;
4. current Runtime Control state is freshly read;
5. current Agent state/version and kill-switch capability are freshly read;
6. the incident still permits containment;
7. the bounded action is still safe and applicable.

Approval is permission to attempt execution, not a cached Runtime Control precondition.

## P1.9d boundary

Restore remains a distinct governed action. An `engage_kill_switch` request or approval must
never authorize restore. Restore requires its own request, human decision, digest, TOCTOU
validation, command, and audit evidence.

## Explicit non-goals for P1.9b

P1.9b does not:

- execute Runtime Control;
- engage or restore a kill switch;
- mutate an Agent;
- mutate an Incident;
- mutate the P1.9a request row;
- call the Policy Model Router;
- call an LLM;
- introduce a generic actuator;
- accept arbitrary runtime configuration;
- implement expiration, cancellation, reconsideration, or supersession;
- implement break-glass approval;
- implement restore authorization.

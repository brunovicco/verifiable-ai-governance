# ADR 0043 — Governed Runtime Actuation Execution

- Status: Accepted
- Date: 2026-08-09
- Scope: P1.9c

## Context

P1.9a creates immutable governed actuation-request genesis evidence. P1.9b appends an independent human approval or rejection decision with mandatory segregation of duties and a Security approval capability. Neither phase changes runtime state.

P1.9c is the first phase allowed to actuate Runtime Control. It must consume only trusted `approved` decision evidence, preserve the existing Runtime Control transition path, prevent approval reuse, perform fresh preflight validation, and remain recoverable when runtime projection or receipt persistence fails partway through the operation.

## Decision

### The only executable action is `engage_kill_switch`

P1.9c does not introduce a generic actuator. The only accepted chain is:

`consider_kill_switch` → `engage_kill_switch` request → Security `approved` decision → Runtime Control `ACTIVE` transition.

The HTTP client cannot select an action, Agent, Incident, expected version, Runtime Control target state, reason, evidence reference, or actuator configuration.

### Explicit execution resource

Execution begins only through:

`POST /api/v1/runtime-assurance-actuation-decisions/{decision_id}/execution`

The body is the closed object `{}`.

The matching GET returns immutable applied execution evidence.

### Approval is necessary but not sufficient

The execution service revalidates the complete trusted chain before every new Runtime Control command:

recommendation → promotion → evaluation → incident → Agent → AI System → request → decision.

The decision must still be `approved`, bound to the same request digest, action, Security approval area, and canonical decision digest.

### Execution authority is separate from approval authority

P1.9b answers whether Security permits the action. P1.9c answers who may operate the governed runtime control after approval.

Execution is limited to the current AI System owner or an administrator. AI System ownership alone cannot approve; Security approval alone does not grant execution authority. The P1.9b requester/approver segregation remains intact; P1.9c does not add a mandatory third distinct human actor.

### Fresh TOCTOU validation

Before creating a new transition, P1.9c reads current Agent and Incident facts and captures the current Agent optimistic version. The execution service then calls the existing `RuntimeControlService.activate()` path with that exact expected Agent version and linked Incident ID.

Runtime Control performs its own authoritative locked re-read and rejects version drift, a closed Incident, a disabled kill switch, an already-engaged switch, or a concurrent pending transition. The governance preflight is therefore advisory to the command; the Runtime Control lock/version check remains authoritative immediately before transition creation.

### Runtime Control remains the single actuator

P1.9c does not write `Agent.kill_switch_engaged` directly and does not create a second actuation mechanism. It invokes only `RuntimeControlService.activate()`.

It never calls `deactivate()` and cannot restore an Agent.

### Decision-bound evidence reference

Every governed Runtime Control transition uses a server-derived evidence reference:

`runtime-assurance-actuation-decision:{decision_id}:{decision_digest}`

This value is not client-controlled. It creates a durable bridge between the approval chain and the existing Runtime Control transition/audit evidence.

### Idempotency and partial-failure recovery

`runtime_assurance_actuation_executions` stores only an immutable receipt for an `APPLIED` transition. It is not a mutable workflow table.

The table enforces one receipt per `decision_id` and one receipt per `runtime_transition_id`.

A retry follows this order:

1. return an existing fully validated receipt;
2. if the decision-bound Runtime Control transition is `APPLIED`, reconstruct and persist the missing receipt without actuating again;
3. if the decision-bound transition is `PENDING`, fail closed with `governed_actuation_pending_reconciliation` and create no duplicate transition;
4. otherwise perform a new fresh Runtime Control activation attempt.

This handles the case where Runtime Control was applied but receipt persistence failed afterward. Runtime Control transition evidence remains the authoritative proof of the effect; the P1.9c receipt can be safely reconstructed from it.

### Canonical execution digest

The execution digest is SHA-256 over canonical JSON and binds:

- execution ID and schema version;
- decision ID and `decision_digest`;
- request ID and `request_digest`;
- governed action;
- Agent, AI System and Incident IDs;
- Runtime Control transition ID and control epoch;
- previous and target Runtime Control states;
- revoked-through Agent version;
- resulting Agent version;
- original Runtime Control execution actor;
- applied timestamp;
- version.

The evidence chain becomes:

`recommendation_digest → request_digest → decision_digest → execution_digest`.

### Applied receipt semantics

P1.9c persists a receipt only for a Runtime Control transition with:

- `previous_state = inactive`;
- `target_state = active`;
- `status = applied`;
- the exact decision-bound evidence reference;
- matching Agent, AI System and Incident IDs.

The resulting Agent version must equal `revoked_through_agent_version + 1`.

### Audit evidence

A directly completed execution appends `runtime_assurance.actuation_executed`.

A receipt reconstructed from an already-applied transition appends `runtime_assurance.actuation_execution_recovered`.

The audit payload is minimized to identifiers and digests. Runtime Control continues to emit its own transition-requested and transition-applied audit events.

### Pending Runtime Control transitions

P1.9c does not create a second transition while the same decision-bound transition is pending. Projection reconciliation remains the existing Runtime Control operational responsibility. A P1.9c receipt is never emitted until the durable Runtime Control transition is `APPLIED`.

### Restore is still separate

An `engage_kill_switch` decision or execution receipt cannot authorize `deactivate()` or restore. Restore requires its own future governed request, independent approval, evidence reference, transition and digest.

### No Router or LLM

No Policy Model Router or LLM participates in approval validation, execution authorization, TOCTOU checks, action selection, digest construction, recovery or Runtime Control actuation.

## Consequences

- P1.9c is the first phase that intentionally changes runtime state.
- The existing Runtime Control service remains the only component allowed to apply the kill switch.
- Approval evidence cannot be reused for more than one governed execution receipt.
- Retries after partial failures do not duplicate Runtime Control transitions.
- Runtime transition evidence and governance evidence become cryptographically linked.
- P1.9d can implement restore without weakening the engage approval boundary.

## Explicit non-goals for P1.9c

P1.9c does not:

- execute rejected decisions;
- allow client-selected actions or Runtime Control state;
- restore or deactivate a kill switch;
- mutate Incident state;
- mutate Agent state outside Runtime Control;
- add a generic actuator framework;
- change approval evidence;
- reverse a human decision;
- implement break-glass approval;
- invoke the Policy Model Router;
- use an LLM;
- treat a `PENDING` Runtime Control transition as successful execution evidence.

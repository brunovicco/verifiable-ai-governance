# ADR 0060 - Advisory Governance Intelligence finding review boundary

- **Status:** Accepted
- **Date:** 2026-08-17
- **Decision owners:** Engineering, architecture, security and AI Governance

## Context

GI-0 through GI-2A establish strict advisory contracts, verified knowledge resolution, bounded
analysis, output validation, audit sequencing and an inert composition root. A valid
`GovernanceFindingEnvelope` is still untrusted and non-authoritative after release. The documented
trust flow requires human or deterministic review before a separate governed decision, but no
application boundary yet defines what reviewing a finding means.

Using an existing approval status for this step would let an advisory interpretation borrow
authority semantics from initiative, control or runtime workflows. Persisting complete findings or
adding a delivery route at the same time would also decide retention, idempotency, access and
untrusted-content rendering before those product requirements exist.

## Decision

### A review disposition is not a governance decision

GI-3 introduces `ReviewGovernanceFinding`, an internal application use case that records only one
of three closed dispositions:

| Disposition | Meaning |
|---|---|
| `accepted_for_consideration` | The reviewer considers the finding suitable input to a separate governed workflow |
| `rejected` | The reviewer declines this advisory finding; no governed subject is rejected |
| `deferred` | The reviewer records no conclusion while more context may be required |

These values cannot represent approval, authorization, compliance, release or runtime permission.
The returned `GovernanceFindingReviewReceipt` is immutable evidence of review activity, not an
instruction to an authoritative use case. GI-3 invokes no governed state transition.

### Revalidation and correlation

The use case accepts an existing `GovernanceFindingEnvelope`, a disposition and authenticated
`GovernanceFindingReviewAccess`. It reconstructs the envelope through the current closed model so
objects created or copied without validation cannot bypass `trust_level="untrusted"` or
`advisory_only=true`. Finding provenance correlation must match the authenticated review context.

Schema revalidation does not prove the finding is true, that its interpretation is correct or that
an external payload was previously released by GI-2. A future delivery consumer must preserve the
GI-2 release boundary or add independently reviewed release verification. GI-3 does not accept raw
source content and does not resolve knowledge again.

### Consumer-owned authorization

`GovernanceFindingReviewAuthorizerPort` receives only actor, subject, finding type and
administrator-access facts. It must return an explicit positive decision before review audit begins.
Denial writes no receipt. Dependency failures and public errors contain no finding statement,
source identity or infrastructure detail.

No concrete subject/role policy is selected because the platform has not decided whether a future
consumer reviews initiative, system, assessment or another subject class. The composition root
therefore remains inert until a separately reviewed consumer supplies this port.

### Content-minimized audit receipt

The complete revalidated envelope is serialized as canonical sorted JSON and bound to the receipt
with lowercase SHA-256. The envelope itself is not persisted. A request-scoped
`SqlAlchemyGovernanceFindingReviewAudit` writes one hash-chained `AuditEvent` containing only:

- review, finding and agent-run IDs;
- finding type and wire schema version;
- the candidate-envelope digest;
- actor, subject, correlation and administrator-access facts;
- disposition and UTC review time.

The event excludes statement, confidence, source references, provider/model identity, prompts,
chain-of-thought, tool output, storage coordinates and source bytes. The same adapter instance owns
append and transaction operations; the receipt is returned only after commit. Cancellation
propagates and triggers best-effort rollback of an incomplete audit transaction.

### Exposure, persistence and replay boundary

GI-3 adds no HTTP endpoint, FastAPI dependency, task, queue, provider, model call, prompt, full
finding table or migration. The review receipt is durable only as minimized audit evidence. There
is no review inbox, finding-content retention or ability to reconstruct a finding from the receipt.

Review IDs identify individual receipts. They are not idempotency keys, and multiple internal
reviews of one finding are not prohibited. Before delivery exposure, a separate decision must
define request idempotency, reviewer concurrency, supersession, retention, deletion, listing and
authorization for the concrete governed subject.

The Governance Finding `1.0` wire schema remains unchanged. Review is a consumer-owned application
concern and does not add authority or review state to the portable finding contract.

## Consequences

### Positive

- advisory review cannot reuse authoritative approval or authorization states;
- unchecked model construction and trace-context substitution fail before authorization;
- a consumer-owned port keeps reviewer policy outside the generic intelligence core;
- durable review evidence is cryptographically bound to an envelope without retaining its content;
- audit failure withholds the receipt, and cancellation cleans up incomplete work;
- provider, delivery and retention choices remain separate reviewable decisions.

### Costs and follow-ups

- a digest-only receipt cannot render or independently reconstruct the reviewed finding;
- no concrete reviewer authorization policy or delivery consumer exists;
- a future remote authorization adapter must define bounded transport timeout and retry behavior;
- repeated reviews have no uniqueness, idempotency or supersession semantics;
- no free-form rationale is retained, avoiding an unbounded untrusted-content channel at this stage;
- a future queue or asynchronous human workflow requires explicit content retention and access rules;
- a future governed action must map the finding through an existing authoritative use case and its
  own validation, segregation-of-duties and audit policy.

## Rejected alternatives

### Treat review acceptance as governance approval

Rejected. `accepted_for_consideration` only admits advisory input to further consideration; it does
not approve a subject, control, assessment or runtime action.

### Reuse initiative or control approval enums

Rejected. Those values carry authoritative lifecycle semantics that an untrusted finding must not
acquire.

### Persist the complete finding for convenience

Rejected for GI-3. Retention, deletion, reviewer access, sensitive derived data and safe rendering
requirements are not yet decided. A digest binds the reviewed envelope without copying its content.

### Put reviewer notes in the audit event

Rejected. Free text would create an unbounded sensitive and prompt-injection-bearing audit channel.
A future rationale contract requires explicit bounds, classification and retention.

### Add a review endpoint with the application boundary

Rejected. Delivery needs concrete subject authorization, idempotency, concurrency, response
semantics and abuse controls. The internal boundary must be reviewable first.

### Add review fields to Governance Finding 1.0

Rejected. Review is consumer state, not producer output. Adding it to the advisory finding would
mix trust zones and violate the immutable version contract.

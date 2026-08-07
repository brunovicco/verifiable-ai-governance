# ADR 0031 — Durable runtime violation evidence

Status: Accepted

## Context

P1.3 makes Policy Model Router a cryptographic enforcement point. A failed authorization returns
HTTP 403, but Governance previously mapped every non-200/422 response to dependency-unavailable.
That loses the distinction between an operational outage and a successful fail-closed denial.

## Decision

P1.4 defines a versioned `RuntimeViolationEnvelope` shared contract and treats a valid Router 403
as a first-class blocked routing outcome.

Governance validates all of the following before trusting the event:

- event schema and canonical SHA-256 digest;
- Router source service;
- correlation ID equals the durable Governance routing-decision ID;
- workflow, task, agent name and workload equal the request that Governance sent;
- authorization ID, key ID, signing digest and scope digest equal the P1.3 artifact;
- error code equals the violation event code;
- model-scope violations report a fully verified authorization state.

A missing, malformed, digest-invalid or binding-mismatched 403 remains
`DEPENDENCY_UNAVAILABLE`, because its evidence cannot be trusted.

A trusted violation is persisted on the existing `model_routing_decisions` row instead of a
parallel table. The row stores the sanitized envelope plus indexed event ID/category/code/digest.
The shared hash-chained audit event stores only violation identifiers and digest. This keeps the
routing attempt, enforcement outcome and violation evidence atomic.

The contract excludes prompts, outputs, documents, headers, API keys, credentials and raw
exception messages.

## Consequences

Operators can query and demonstrate runtime governance denials without depending on logs.
`BLOCKED` now means an enforceable policy/governance denial, while `DEPENDENCY_UNAVAILABLE`
continues to mean the external decision boundary could not be trusted.

P1.4 does not assign incident severity, automatically create incidents, propagate OpenTelemetry
attributes, or engage the kill switch. Those remain separate lifecycle steps.

# Runtime violation evidence

P1.4 stores trusted Policy Model Router denials directly on the durable routing attempt.

## Operator queries

Filter routing decisions by:

- `violation_event_id` for one exact enforcement event;
- `violation_category` for authorization/replay/request-binding/provenance/model-scope groups;
- `violation_code` for a bounded machine-readable denial reason.

The public routing-decision API also returns the validated `runtime_violation` envelope.

## Triage boundary

A routing decision with `outcome=blocked` and `runtime_violation` present means the Router denial
was structurally valid and bound to the request Governance sent.

A decision with `outcome=dependency_unavailable` and `router_unavailable` means the Router failed,
was unreachable, or returned evidence Governance could not trust. Do not treat it as a confirmed
policy violation.

## Privacy

Violation payloads contain identifiers and digests only. Do not extend the contract with prompts,
model outputs, documents, request headers, API keys, provider credentials or exception strings.

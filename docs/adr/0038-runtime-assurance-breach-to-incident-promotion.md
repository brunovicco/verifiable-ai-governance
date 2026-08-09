# ADR 0038 — Governed Runtime Assurance breach-to-incident promotion

Status: Accepted  
Date: 2026-08-09

## Context

P1.8a introduced deterministic Runtime Assurance evaluations over sanitized P1.7 telemetry.
A `breached` evaluation is durable, reproducible evidence, but deliberately has no side effect on
the incident lifecycle or Runtime Control.

The platform already has a mature incident aggregate with:

- AI System owner/admin authorization;
- explicit lifecycle transitions;
- optimistic versioning;
- remediation;
- temporary exceptions;
- kill-switch operations;
- tamper-evident audit events.

P1.8b must connect Runtime Assurance evidence to that existing incident lifecycle without creating
a parallel incident model or turning detection into an automatic actuator.

## Decision

P1.8b adds an explicit promotion command:

```text
POST /api/v1/runtime-assurance-evaluations/{evaluation_id}/incident-promotion
```

The command accepts an empty, closed request object. Arbitrary action fields are rejected.

Only a persisted `breached` evaluation with controlled breach reasons and severity can be promoted.

Promotion authority remains identical to normal incident authority:

- AI System owner; or
- administrator.

An Agent owner who is not also the AI System owner does not gain incident-management authority.

## Deduplication

A deterministic `breach_fingerprint` is SHA-256 over:

```json
{
  "schema_version": "1.0",
  "agent_id": "<agent-id>",
  "breach_reasons": ["<sorted controlled reason codes>"]
}
```

Policy version and severity are deliberately excluded.

This means successive policy versions or severity observations for the same Agent and breach-reason
family remain linked to the same active operational incident.

Under an AI System row lock the promotion command:

1. checks whether the exact evaluation was already promoted;
2. resolves active incidents linked to the same Agent/fingerprint;
3. fails closed if more than one active incident matches;
4. creates a new incident when none exists;
5. otherwise links to the existing incident;
6. escalates the existing incident severity when the new breach is strictly more severe;
7. persists immutable promotion lineage;
8. appends minimized audit evidence;
9. commits the incident/link/audit changes atomically.

Closed incidents are excluded from deduplication. A later breached evaluation may therefore create a
new incident after the previous lifecycle has been closed.

## Idempotency

`evaluation_id` is unique in `runtime_assurance_incident_promotions`.

Replaying promotion for the same evaluation returns the existing linkage and does not:

- create another incident;
- create another promotion record;
- append duplicate audit events;
- mutate incident severity.

## Severity escalation

Deduplication does not hide a worsening condition.

Severity order is:

```text
low < medium < high < critical
```

If the new breached evaluation is more severe than the active linked incident, the same incident is
optimistically versioned forward and an `incident.severity_escalated` audit event is appended.

Equal or lower severity produces only a deduplicated linkage.

## Audit evidence

A newly created incident uses the existing `incident.reported` action with minimized Runtime
Assurance provenance.

A severity increase emits:

```text
incident.severity_escalated
```

Every new evaluation linkage emits:

```text
runtime_assurance.incident_promoted
```

The promotion audit payload contains only structural identifiers, disposition, breach fingerprint
and the P1.8a evidence digest.

## Safety boundary

P1.8b does **not**:

- automatically promote every breach;
- automatically engage a kill switch;
- automatically contain or close incidents;
- revoke runtime authorization;
- invoke an LLM;
- persist prompts, completions, exception messages, application payloads or business data;
- broaden incident-management authority to Agent owners.

Runtime Control remains a separate governed action.

## Follow-up

P1.8c may derive deterministic response recommendations from the linked incident and breach
evidence, including whether kill-switch engagement should be considered. Recommendations remain
non-actuating unless a later ADR explicitly defines an authorized automatic-control boundary.

# Runtime Assurance Incident Promotion

P1.8b explicitly promotes persisted P1.8a breach evidence into the existing governed incident
lifecycle.

## Preconditions

The evaluation must:

- exist;
- have `outcome=breached`;
- contain at least one controlled breach reason;
- contain a governed severity.

The caller must be the AI System owner or an administrator.

## Promote

```bash
curl -sS --fail-with-body   -X POST   "http://127.0.0.1:8000/api/v1/runtime-assurance-evaluations/<evaluation-id>/incident-promotion"   -H "Content-Type: application/json"   -H "X-User-Id: <ai-system-owner>"   -d '{}' | jq
```

The response is content-minimized and includes:

- promotion ID;
- evaluation ID;
- Agent/System IDs;
- incident ID;
- breach fingerprint;
- disposition;
- promotion actor/time;
- evidence digest;
- current incident status/severity/version.

It does not return the incident description or any Runtime Telemetry payload.

## Dispositions

```text
created
deduplicated
severity_escalated
```

`created` means no active incident existed for the Agent/breach fingerprint.

`deduplicated` means the evaluation was linked to an already active incident without changing its
severity.

`severity_escalated` means the same active incident was retained but its severity moved upward.

## Read linkage

```bash
curl -sS --fail-with-body   "http://127.0.0.1:8000/api/v1/runtime-assurance-evaluations/<evaluation-id>/incident-promotion"   -H "X-User-Id: <ai-system-owner>" | jq
```

## Deduplication semantics

The fingerprint uses only:

```text
Agent ID
+ sorted controlled breach reason codes
```

It intentionally excludes policy version and severity.

A new evaluation with the same breach family links to the same incident while that incident is:

```text
open
contained
remediating
```

A `closed` incident is not reused.

## Idempotency

Retrying the exact same evaluation promotion returns the existing record and creates no duplicate
incident or audit event.

## Safety checks

After promotion, verify Runtime Control was not mutated:

```sql
SELECT count(*)
FROM runtime_control_transitions
WHERE agent_id = '<agent-id>';
```

P1.8b never automatically engages the kill switch.

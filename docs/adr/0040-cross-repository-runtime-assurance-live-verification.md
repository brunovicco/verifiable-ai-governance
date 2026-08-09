# ADR 0040 — Live cross-repository Runtime Assurance evidence verification

## Status

Accepted.

## Context

P1.7 established sanitized terminal runtime telemetry from the real Credit Desk
producer through `a2a-otel-kit` into Governance. P1.8a converts bounded telemetry
into deterministic assurance evidence, P1.8b explicitly promotes breached evidence
into the governed Incident lifecycle, and P1.8c generates deterministic advisory
response recommendations.

Unit and API tests prove each boundary independently. The portfolio also needs one
reproducible proof that the complete evidence chain works with the real producer and
that the final `consider_kill_switch` recommendation does not silently become a
runtime actuator.

## Decision

Add a P1.8d live verification harness in the Governance repository.

The harness:

1. requires the merged P1.8c Governance baseline;
2. requires the merged P1.7c Credit Desk telemetry baseline through the reused P1.7 probe;
3. verifies the Credit Desk runtime resolves `a2a-otel-kit==0.5.0`;
4. emits one completed and one failed terminal task from the real Credit Desk server;
5. verifies sanitized telemetry and W3C trace/span correlation;
6. configures a bounded two-sample Runtime Assurance policy;
7. proves the fresh pair yields a critical `failure_rate_exceeded` breach;
8. explicitly promotes the evaluation through P1.8b;
9. generates the P1.8c advisory recommendation;
10. requires `investigate_failures`, `prepare_containment`, and `consider_kill_switch`;
11. proves recommendation replay is idempotent;
12. verifies telemetry, assurance, promotion, and recommendation audit evidence;
13. compares Incident, Agent, and Runtime Control state before and after advice generation;
14. writes a content-minimized JSON evidence report.

An already-active matching incident is not closed merely to force a `created`
disposition. `created`, `deduplicated`, and `severity_escalated` are all valid
governed outcomes when their lineage and final critical state are valid.

## Deployment reproducibility

Docker Compose now forwards the existing telemetry-ingestion settings:

- `RUNTIME_TELEMETRY_INGEST_ENABLED`
- `RUNTIME_TELEMETRY_API_KEYS_JSON`

Both remain safe by default: ingestion is disabled and the credential map is empty.

## Safety boundary

The harness never:

- engages or restores a kill switch;
- creates Runtime Control transitions;
- closes an existing Incident to manufacture test state;
- deletes prior telemetry, evaluations, incidents, promotions, or recommendations;
- persists telemetry credentials in the report;
- persists Credit Desk business payloads in the report.

If the canonical Agent begins with its kill switch engaged, the harness fails
preflight rather than mutating the environment.

## Consequences

P1.8 now has one executable evidence chain from a real cross-repository producer to
deterministic governance advice while preserving the separation between evidence,
recommendation, and runtime actuation.

# ADR 0036 — Cross-repository live verification for sanitized runtime telemetry

Status: Accepted  
Date: 2026-08-09

## Context

P1.7a introduced a closed, authenticated runtime-telemetry ingestion boundary in Verifiable AI
Governance. P1.7b published the opt-in `GovernanceRuntimeTelemetrySink` in `a2a-otel-kit` 0.5.0.
P1.7c made `decisao-agent` emit terminal evaluation evidence through that sink.

Repository-local tests prove each contract independently, but they do not prove that the real
producer, released library and Governance API interoperate with the same Agent binding, machine
credential, W3C trace context, normalized persistence and hash-chained audit record.

## Decision

P1.7d adds an opt-in live verification harness owned by the Governance repository.

The live topology is:

```text
Credit Desk decisao-agent
    |
    | StructuredEvent
    v
a2a-otel-kit 0.5.0 GovernanceRuntimeTelemetrySink
    |
    | authenticated POST /runtime-telemetry
    v
Verifiable AI Governance
    |
    +--> normalized runtime_telemetry_events row
    |
    +--> runtime_telemetry.ingested audit event
             |
             +--> canonical SHA-256 hash + previous_hash link
```

The harness starts the real Credit Desk A2A server and sends exactly two structural scenarios:

1. a healthy application that reaches `TASK_STATE_COMPLETED`;
2. malformed JSON that reaches `TASK_STATE_FAILED`.

It then verifies through the Governance read API that exactly one telemetry event exists for each
A2A `(context_id, task_id)` pair.

## Required invariants

For the successful event:

- `event_name=decisao_agent.evaluation.completed`;
- `event_outcome=success`;
- `correlation_id=context_id`;
- `request_id=task_id`;
- active 32-hex W3C `trace_id`;
- active 16-hex W3C `span_id`.

For the failed event:

- `event_name=decisao_agent.evaluation.failed`;
- `event_outcome=failure`;
- `error_type=ValidationError`;
- the same structural correlation guarantees.

Both events must be normalized, use source schema version 1, expose a canonical payload digest and
contain no application snapshot, model content, authorization material or telemetry credential.

For each event the harness queries the Governance database and verifies:

- exactly one `runtime_telemetry.ingested` audit row;
- the minimized audit payload exactly matches the P1.7a contract;
- the audit event hash recomputes from the canonical Governance formula;
- `previous_hash`, when present, resolves to a real preceding audit row.

## Security boundary

The telemetry API key is supplied only through `P1_7_TELEMETRY_API_KEY` in the harness process and
is passed to the Credit Desk subprocess through its expected environment variable. It is never
accepted as a command-line argument, printed, copied into the report or written to source control.

The report contains identifiers, trace/span IDs, event names, durations, digests and audit hashes
only. No request body or raw credit opinion is retained.

The harness does not:

- add a production endpoint;
- write telemetry or audit rows directly;
- bypass the P1.7a machine-authentication boundary;
- change the Credit Desk deterministic decision;
- require a Router or LLM to succeed;
- mutate Runtime Control state.

## Consequences

P1.7 has an executable proof that sanitized operational evidence crosses the real repository
boundaries and becomes tamper-evident Governance evidence.

The live verifier remains outside default CI because it requires two repositories, a running
Governance API, the canonical demo database and a local machine credential.

# ADR-0035 — Sanitized runtime telemetry ingestion

- Status: Accepted
- Date: 2026-08-08

## Context

`a2a-otel-kit` deliberately emits metadata-only telemetry with deny-by-default attributes and a
versioned structured-event vocabulary. Governance needs durable runtime evidence without turning
its database into a log lake or creating a second path for prompts, messages, artifacts, headers,
credentials, or model outputs.

## Decision

P1.7a introduces a narrow Governance-owned ingestion contract and persistence model.

The contract accepts only bounded structural fields already compatible with the privacy posture of
`a2a-otel-kit`: source schema version, event identity/time/name/outcome, service identity,
trace/span identifiers, correlation/request identifiers, retry/duration, HTTP method/status and a
safe error type.

There is intentionally no arbitrary `attributes`, `payload`, `message`, `prompt`, `artifact`,
request body, response body or header map.

Each event is bound to a governed Agent through the URL and a per-agent machine credential.
Governance computes a canonical SHA-256 digest over the normalized event and uses the caller's
`event_id` for idempotency. Reusing an event ID with different evidence fails with conflict.

The durable row stores only the normalized fields and digest. A minimized
`runtime_telemetry.ingested` event is appended to the existing hash-chained audit log in the same
transaction.

Human reads remain restricted to the Agent owner, AI System owner or an administrator.

## Consequences

- P1.7b can add an opt-in `a2a-otel-kit` Governance sink without changing the Governance contract.
- Raw OTLP traces remain observability data; this table is governance evidence, not a tracing
  backend.
- No prompt/content capture is introduced.
- Machine credentials are deployment configuration and are never persisted in telemetry rows or
  audit payloads.
- Dashboard aggregation is intentionally deferred until real telemetry exists end-to-end.

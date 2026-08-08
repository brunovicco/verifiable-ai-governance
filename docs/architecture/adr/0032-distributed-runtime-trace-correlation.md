# ADR 0032 — Correlate governed runtime evidence with distributed traces

Status: Accepted  
Date: 2026-08-07

## Context

P1.4 made Router authorization denials durable by binding each violation to the
Governance routing-decision ID through `correlation_id`. Operational diagnosis
still required manually joining logs from different services.

Governance currently runs Python 3.12. `a2a-otel-kit` 0.4.2 requires Python
3.13 or newer, so importing that package here would raise the application
runtime baseline only for observability.

## Decision

Use W3C Trace Context (`traceparent` and `tracestate`) for transient distributed
trace propagation and keep the existing Governance routing-decision ID as the
durable audit-to-trace correlation key.

Governance uses a small OpenTelemetry SDK bridge on Python 3.12. The Router and
Credit Desk use `a2a-otel-kit` directly.

The bridge is intentionally narrow:

- OTLP/HTTP export is disabled by default;
- only content-free allowlisted attributes are recorded;
- exporter failures never change a governance or routing outcome;
- trace context is never used as an authorization signal;
- no prompt, response, document, token, API key, authorization envelope, or
  customer content is recorded;
- no P1.4 contract or database schema changes are required.

## Consequences

A runtime violation can be located in the tracing backend using the same
`correlation_id` already committed to durable evidence. Trace storage remains
operational telemetry; PostgreSQL audit evidence remains the system of record.

If `a2a-otel-kit` later supports Python 3.12, Governance may replace the bridge
without changing the W3C boundary or the durable evidence model.

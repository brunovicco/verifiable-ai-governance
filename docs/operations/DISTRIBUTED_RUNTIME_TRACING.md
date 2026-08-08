# P1.5 distributed runtime tracing

The governed runtime path uses two independent identifiers:

- **W3C trace context**: transient parent/child relationship across services;
- **Governance routing decision ID**: durable `correlation_id` stored in P1.4
  evidence and emitted as a safe trace attribute.

## Governance configuration

```env
OTEL_ENABLED=true
OTEL_ENDPOINT=http://otel-collector:4318/v1/traces
OTEL_TIMEOUT_SECONDS=5
```

Telemetry is disabled by default. The OTLP collector should own any downstream
vendor credentials; do not place exporter credentials in span attributes.

## Expected trace

```text
Credit Desk / A2A request
  -> Governance HTTP request
     -> Governance policy-model-router client
        -> policy-model-router HTTP request
           -> runtime authorization / deterministic routing
```

A Router violation event remains digest-bound to the Governance routing
decision through `correlation_id`. Search the tracing backend for that same
correlation ID to reconstruct the operational path.

## Privacy

Allowed span attributes are bounded operational metadata only. Prompts,
outputs, financial payloads, documents, signed authorizations, bearer tokens,
API keys and arbitrary request headers are excluded.

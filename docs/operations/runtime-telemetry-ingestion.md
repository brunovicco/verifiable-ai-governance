# Runtime telemetry ingestion operations

## Purpose

P1.7a provides the Governance-side durable evidence boundary for future `a2a-otel-kit` adoption.
It does not yet configure an OTel Collector or modify `a2a-otel-kit`.

## Configuration

```env
RUNTIME_TELEMETRY_INGEST_ENABLED=true
RUNTIME_TELEMETRY_API_KEYS_JSON={"<agent-uuid>":"<secret>"}
RUNTIME_TELEMETRY_LIST_LIMIT=100
```

Keep the JSON mapping in a secret manager or deployment secret. Do not commit it.

## Ingest endpoint

```text
POST /api/v1/agents/{agent_id}/runtime-telemetry
X-Telemetry-Api-Key: <per-agent-secret>
Content-Type: application/json
```

The body is a closed schema. Unknown fields are rejected. There is no generic attribute bag.

## Query endpoint

```text
GET /api/v1/agents/{agent_id}/runtime-telemetry
```

The normal Governance user authentication path applies. Only the Agent owner, AI System owner or
administrator can read the evidence.

## Idempotency

- same `event_id` + same canonical digest: existing record is returned without a second audit event;
- same `event_id` + different agent or digest: `409 Conflict`;
- unknown agent: `404`;
- ingestion disabled: `503`;
- missing/invalid machine credential: `403`.

## Privacy boundary

Never add prompt, completion, message, document, artifact, URL, arbitrary headers, exception
message, credentials or raw request/response bodies to this contract. Such data belongs in
application-owned evidence/artifact stores, not telemetry.

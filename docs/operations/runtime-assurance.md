# Runtime Assurance Operations

P1.8a converts sanitized runtime telemetry into deterministic, governed SLO evidence.

## Create a policy

```bash
curl -sS -X PUT \
  http://127.0.0.1:8000/api/v1/agents/<agent-id>/runtime-assurance-policy \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: <agent-or-system-owner>' \
  -d '{
    "enabled": true,
    "lookback_seconds": 300,
    "evaluation_sample_size": 100,
    "minimum_samples": 20,
    "max_failure_rate": 0.05,
    "max_p95_duration_ms": 1000,
    "max_consecutive_failures": 3,
    "breach_severity": "high",
    "expected_version": null
  }' | jq
```

Updates must send the current persisted version in `expected_version`; missing/stale versions fail
with HTTP 409.

## Evaluate

```bash
curl -sS -X POST \
  http://127.0.0.1:8000/api/v1/agents/<agent-id>/runtime-assurance-evaluations \
  -H 'X-User-Id: <agent-or-system-owner>' | jq
```

Outcomes: `insufficient_data`, `healthy`, `breached`.

Controlled breach reasons:

```text
failure_rate_exceeded
p95_duration_exceeded
consecutive_failures_exceeded
```

`source_event_ids` is the bounded ordered set of terminal P1.7 telemetry rows used in the
calculation. `evidence_digest` binds Agent/system/initiative, policy version, evaluation window,
metrics, outcome/reasons/severity and those source event IDs.

A `breached` result is evidence, not an actuator. P1.8a never opens an incident automatically,
engages a kill switch, calls the Policy Model Router, invokes an LLM, mutates Credit Desk, or stores
business payloads. Incident promotion is deferred to P1.8b.

# Runtime Assurance response recommendations

P1.8c turns a governed Runtime Assurance incident promotion into deterministic,
advisory-only response guidance.

## Endpoint

Generate or replay the immutable recommendation set:

```http
POST /api/v1/runtime-assurance-incident-promotions/{promotion_id}/response-recommendations
Content-Type: application/json

{}
```

Read persisted recommendation evidence:

```http
GET /api/v1/runtime-assurance-incident-promotions/{promotion_id}/response-recommendations
```

## Authorization

Only the AI System owner or an administrator may generate or read these
recommendations.

## Rules

| Evidence | Recommendation |
|---|---|
| failure-rate or consecutive-failure breach | `investigate_failures` |
| p95-duration breach | `investigate_latency` |
| high or critical incident severity | `prepare_containment` |
| critical + kill switch enabled + not engaged | `consider_kill_switch` |
| low or medium incident severity | `monitor_recovery` |

The returned object is always `advisory_only=true`.

## Operational invariant

No endpoint in P1.8c executes the recommendation. In particular,
`consider_kill_switch` never calls Runtime Control. Operators must use the existing
Incident/Runtime Control workflow and its authorization checks if they decide to
act.

## Evidence verification

For audit or incident review, verify that the recommendation record contains:

- the expected promotion/evaluation/incident identifiers;
- the same `source_evidence_digest` as the source Runtime Assurance evaluation;
- the frozen incident version/status/severity;
- the frozen Agent kill-switch availability and state;
- policy ID/version/digest;
- controlled actions and rationale codes;
- a 64-character `recommendation_digest`;
- `advisory_only=true`.

The corresponding hash-chained audit action is:

```text
runtime_assurance.response_recommended
```

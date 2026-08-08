# Runtime kill switch threat model

## Security objective

An emergency Runtime Control transition must stop Governance from producing an `ALLOWED` model-routing result and must create a monotonic shared state that P1.6b can enforce in `policy-model-router` without waiting for the Runtime Authorization TTL.

## Trust boundaries

- PostgreSQL is the durable Governance system of record.
- Redis is the low-latency runtime safety-plane projection, not a second source of truth.
- Governance owns Redis writes. Router-side P1.6b should use read-only credentials.
- The existing Ed25519 Runtime Authorization remains independently verified; Runtime Control does not replace signature, binding, provenance, or replay checks.
- Trace context is telemetry and is never authoritative control state.

## Threats and controls

| Threat | Control |
|---|---|
| A valid authorization was issued immediately before emergency stop | `active` runtime projection denies immediately in P1.6b; Governance rechecks pre/post Router in P1.6a |
| Restore resurrects a pre-stop authorization | `revoked_through_agent_version` is monotonic and compared with the already-signed `subject.agent_version` |
| Older writer overwrites a newer runtime state | Redis Lua CAS rejects lower epochs |
| Same epoch is rewritten with different content | CAS rejects same-epoch divergence; only byte-identical replay is idempotent |
| Redis is unavailable or contains malformed state | Fail closed; Governance does not assume `inactive` |
| Redis state is missing or strictly older than durable state | Governance may repair only from unambiguous durable evidence |
| Redis has an unexplained newer epoch | Fail closed; no forced overwrite |
| DB transition commits but Redis projection fails | Transition remains `pending`; issuance and accepted result propagation are blocked until reconciliation |
| Redis applies but DB finalization fails | Runtime state remains fail-safe; durable transition remains recoverable through reconciliation |
| Concurrent operator command races reconciliation/finalization | Canonical DB lock order is Agent then Transition; per-agent epoch is unique |
| Operator without authority attempts activate/deactivate | AI-system owner, Agent owner, or administrator boundary is enforced |
| Incident workflow delays emergency containment | Direct activation does not require an Incident; `incident_id` is optional correlation only |
| Timer accidentally re-enables an unsafe agent | No automatic expiry or auto-restore is implemented |
| Redis write credential compromise | Treat writer access as safety-plane authority; isolate network, require TLS outside local/test, rotate credentials, and give Router read-only credentials in P1.6b |
| Redis key eviction causes implicit allow | No TTL; missing key is fail closed in strict runtime enforcement |
| Prompt/output/secret leakage through control evidence | Transition/audit payload is structural and bounded; prompt/output/credentials are excluded |
| Telemetry outage changes control decision | OTel remains non-authoritative and cannot weaken Runtime Control |

## Residual risk in P1.6a

P1.6a protects the Governance-mediated path. A previously issued authorization sent directly to the P1.5 Router can still be accepted until P1.6b adds Router-side Redis enforcement. Do not claim end-to-end immediate revocation until P1.6b is deployed and the bootstrap command has projected every governed Agent.

## P1.6b acceptance criteria

Router enforcement must:

1. verify the existing Runtime Authorization signature/binding/provenance first;
2. read the agent Runtime Control snapshot before replay consumption/routing;
3. deny `kill_switch_engaged` when state is `active`;
4. deny `runtime_authorization_revoked` when signed `agent_version <= revoked_through_agent_version`;
5. deny `runtime_control_unavailable` for missing, malformed, unavailable, or otherwise untrusted control state;
6. preserve Runtime Violation evidence and W3C trace propagation without using trace IDs as durable identity.

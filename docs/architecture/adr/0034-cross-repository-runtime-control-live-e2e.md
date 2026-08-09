# ADR 0034 — Cross-repository live verification for Runtime Control

Status: Accepted  
Date: 2026-08-08

## Context

P1.6a established Governance as the durable Runtime Control authority. P1.6b made
`policy-model-router` consume the monotonic Redis projection before replay-token
consumption. P1.6c proved that downstream Credit Desk narrative generation fails
closed while its deterministic credit decision remains unchanged.

Those repository-local tests are necessary but do not prove that one real signed
authorization can cross the actual HTTP and Redis boundaries during an emergency
transition.

A simple "activate, then ask Governance to route" test is insufficient. Governance
intentionally checks Runtime Control before issuing an authorization, so such a test
never reaches the Router and therefore cannot prove Router-side enforcement.

## Decision

P1.6d adds an opt-in live verification harness owned by the Governance repository.

The harness uses a bounded local barrier proxy between Governance and the real Router:

```text
Governance
   |
   | signed authorization B
   v
Barrier proxy ---- activate Runtime Control through Governance
   |
   | exact unmodified B
   v
policy-model-router ---- shared Redis projection
```

The barrier activates the kill switch only after Governance has completed its
pre-check and issued B, but before B reaches the Router. This creates a controlled
TOCTOU window without weakening production code.

The harness then verifies:

1. authorization A routes normally and is consumed;
2. B is issued under the pre-kill Agent version;
3. Runtime Control becomes active before B reaches the Router;
4. Router denies B as `kill_switch_engaged`;
5. Governance validates and persists the Router `RuntimeViolation`;
6. while active, the real Credit Desk preserves its deterministic credit decision
   and omits the optional LLM narrative;
7. Governance restores the Agent while retaining the revocation floor;
8. the exact, still-unconsumed B is sent again and is denied as
   `runtime_authorization_revoked`, not replay;
9. fresh authorization C carries a higher signed `agent_version` and routes normally.

## Security boundary

The barrier is test infrastructure only. It:

- runs only when explicitly invoked;
- does not change the signed authorization;
- forwards only the Router headers required by the existing contract;
- does not log API keys, signatures, request bodies or customer content;
- stores only identifiers and versions in its JSON report;
- uses the existing Governance administrative endpoint to change Runtime Control;
- does not write the Redis projection directly.

No new production endpoint, signed claim, secret store, control plane or trust
relationship is introduced.

## Consequences

P1.6 now has an executable cross-repository proof of the exact race the dual
Governance/Router enforcement is designed to close.

The live verifier remains outside the default CI path because it requires three
repositories, runtime signing material, Redis and running services. Pure tests cover
the harness parser and fail-closed invariants in normal CI.

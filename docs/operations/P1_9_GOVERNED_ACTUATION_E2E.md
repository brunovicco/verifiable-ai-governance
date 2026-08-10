# P1.9e Live Governed Actuation E2E

## Purpose

P1.9e is the live proof for the complete governed containment and recovery chain built in P1.8
and P1.9. It adds no production API, database table, or runtime actuator.

The harness proves this path with real services:

```text
Credit Desk
  -> a2a-otel-kit telemetry
  -> Runtime Assurance BREACHED
  -> governed Incident
  -> advisory consider_kill_switch
  -> P1.9a actuation request
  -> P1.9b independent Security approval
  -> P1.9c governed Runtime Control activation
  -> routing blocked by kill_switch_engaged
  -> remediation evidence
  -> P1.9d restore request
  -> new independent Security approval
  -> governed Runtime Control restoration
  -> fresh routing allowed again
```

The live harness intentionally does not call the legacy direct kill-switch or low-level
Runtime Control command endpoints.

## Required repositories

Use local checkouts for:

- `verifiable-ai-governance` containing merge `27212f0e04a138cfbb51601c1edf88e9964e74b1`;
- `multi-agent-credit-desk` containing the baseline already required by the P1.7 live producer;
- `policy-model-router` configured with the same runtime-authorization trust material used by the
  existing P1.6 live integration.

The Credit Desk path must use its installed `a2a-otel-kit` runtime package.

## Governance configuration

The Governance API must run in a local/test setup with:

- development authentication enabled;
- Runtime Control enabled and backed by Redis;
- Policy Model Router enabled;
- the Router base URL pointing to the real Router process;
- Runtime Telemetry ingestion enabled;
- the telemetry API-key map containing the canonical Agent ID as the key.

`RUNTIME_TELEMETRY_API_KEYS_JSON` is keyed by `agent_id`, because ingestion authenticates each
machine credential against the requested Agent.

Example after reading the canonical Agent ID:

```bash
cd /Users/brunovicco/Projects/verifiable-ai-governance

AGENT_ID="$(python - <<'PY'
import json
from pathlib import Path
print(json.loads(Path('artifacts/demo/canonical-seed-manifest.json').read_text())['agent_id'])
PY
)"

export P1_7_TELEMETRY_API_KEY='<local-test-key>'
export RUNTIME_TELEMETRY_INGEST_ENABLED=true
export RUNTIME_TELEMETRY_API_KEYS_JSON="{\"${AGENT_ID}\":\"${P1_7_TELEMETRY_API_KEY}\"}"
export POLICY_MODEL_ROUTER_ENABLED=true
export POLICY_MODEL_ROUTER_BASE_URL=http://host.docker.internal:8082
```

Do not commit the telemetry secret or generated environment values.

Start or recreate the Governance API using the project's normal local Docker Compose workflow so
those environment variables are present in the API process.

## Policy Model Router

Run the real Router on port `8082`. Its `/readyz` endpoint must be healthy.

The Router must use the same P1.3/P1.6 runtime-authorization trust configuration already proven by
the cross-repository runtime-control harness. In particular, when runtime authorization is
required, configure the Router's `RUNTIME_AUTHORIZATION_*` trust values and its per-agent `API_KEYS`
for the canonical Agent identity.

The Router also needs access to the same Runtime Control Redis projection when its runtime-control
validation is enabled. Reuse the existing P1.6 configuration rather than generating new signing
keys or trust metadata for P1.9e.

A simple reachability check is:

```bash
curl --fail http://127.0.0.1:8082/readyz
```

The P1.9e harness performs a real preflight routing decision and fails if Governance is not actually
reaching Policy Model Router.

## Canonical data

The harness expects the canonical demo Agent to start with:

```text
kill_switch_enabled = true
kill_switch_engaged = false
AI System owner      = demo.requester   # unless --user-id is overridden
```

Run the canonical seed workflow if the manifest or governed runtime assets are absent.

P1.9e intentionally fails instead of silently restoring a pre-existing active kill switch.

## Run

From the Governance repository:

```bash
export P1_7_TELEMETRY_API_KEY='the-same-local-secret-configured-in-governance'

uv run python -m scripts.verify_p1_9_governed_actuation_e2e \
  --credit-desk-repo /Users/brunovicco/Projects/multi-agent-credit-desk \
  --router-url http://127.0.0.1:8082
```

If the Credit Desk checkout is elsewhere, change only `--credit-desk-repo`.

The default local identities are:

```text
requester/executor: demo.requester
Security approver:  demo.security
```

The Security identity is sent with local `X-User-Areas: security`. The harness also proves that the
requester cannot self-approve even when that request carries the Security area.

## Expected output

A successful run ends with:

```text
[p1.9e] PASSED
[p1.9e] report: artifacts/e2e/p1.9-governed-actuation-live-report.json
[p1.9e] governed engage blocked routing; governed restore re-enabled fresh routing
[p1.9e] engage and restore used independent Security approvals and evidence chains
```

## Live invariants

The harness requires all of the following:

1. Fresh Router-backed routing is `allowed` before containment.
2. Real Credit Desk terminal events reach Governance through the P1.7 telemetry path.
3. Runtime Assurance evaluates exactly the fresh success/failure evidence as `breached`.
4. Incident promotion and advisory recommendation remain explicit.
5. Recommendation generation itself causes zero Runtime Control mutation.
6. Engage request replay returns the same immutable request.
7. The requester cannot self-approve the engage request.
8. An independent Security principal approves the request.
9. Governed engage execution creates exactly one new Runtime Control transition.
10. Routing while contained is blocked with `reason_code=kill_switch_engaged`.
11. A remediation plan moves the Incident to `remediating`.
12. Restore request is bound to the P1.9c execution and remediation digest.
13. The requester cannot self-approve the restore request.
14. Restore requires a new Security decision with a digest distinct from engage approval.
15. Governed restore creates exactly one additional Runtime Control transition.
16. Replaying engage or restore execution creates no extra transition.
17. Fresh routing after restore is Router-backed and `allowed` again.
18. Governance audit evidence for request/approval/execution on both paths has valid hash-chain
    linkage.

## Report safety

The generated report contains only allowlisted structural identifiers, states, policy metadata,
versions, digests, routing outcomes, and audit hashes.

It does not intentionally persist:

- prompts;
- completions or model output;
- Credit Desk business payloads;
- annual revenue or bureau data;
- decision reasons supplied by humans;
- remediation narrative text;
- API keys;
- credentials;
- authorization tokens.

The existing P1.8 report-safety validator is reused and the telemetry secret is checked before the
report is written.

## Failure handling

Treat a failure as evidence that the complete path is not proven. Do not bypass failed preconditions
by calling direct Runtime Control endpoints.

If the run stops after engagement, inspect the governed evidence and Runtime Control state before
retrying. P1.9c/P1.9d execution endpoints are idempotent and handle their documented partial-failure
recovery rules; the harness itself does not invent cleanup transitions.

If a transition is pending reconciliation, reconcile it through the existing Runtime Control
operations path, then rerun from a clean canonical scenario.

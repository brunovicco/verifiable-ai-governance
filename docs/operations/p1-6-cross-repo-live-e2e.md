# P1.6 cross-repository live E2E

This runbook closes P1.6 with a live proof across:

- `verifiable-ai-governance`;
- `policy-model-router`;
- `multi-agent-credit-desk`.

The test deliberately creates a controlled race between Governance authorization
issuance and Router enforcement. It does **not** disable replay protection and does
not write Runtime Control state directly to Redis.

## Required repository state

Use the merged P1.6 baselines or later compatible commits:

```text
verifiable-ai-governance  c8a44845fdca8ef5a60746a3663a50e23f3728dd or P1.6d descendant
policy-model-router       0344f7410fa68fbd8a61fb5d949f5d4dcf0c9166
multi-agent-credit-desk   aef5ff3621b94d0e677b229de55e1b9dce3ae8c5
```

Run the normal dependency sync in every repository before the live test.

For Credit Desk:

```bash
cd /Users/brunovicco/Projects/multi-agent-credit-desk
uv sync --frozen --all-groups --all-packages
```

## Runtime topology

The important topology is:

```text
Credit Desk :8199
      |
      v
Governance :8000
      |
      v
Barrier proxy :18082
      |
      v
Router :8082
      |
      v
shared Runtime Control Redis :6380
```

Governance must use:

```env
POLICY_MODEL_ROUTER_ENABLED=true
POLICY_MODEL_ROUTER_BASE_URL=http://127.0.0.1:18082
```

The Router must read the **same Redis database** projected by Governance:

```env
REDIS_URL=redis://127.0.0.1:6380/0
RUNTIME_CONTROL_REQUIRED=true
RUNTIME_CONTROL_REDIS_KEY_PREFIX=verifiable-ai-governance:runtime-control:v1:agent:
```

Governance and Router must also use matching Runtime Authorization trust material and
policy/control-catalog provenance, exactly as required by P1.3/P1.6b.

Do not point the live test at a production environment.

## Prepare the canonical demo

Run migrations and the canonical seed using the same database as the Governance API.

```bash
cd /Users/brunovicco/Projects/verifiable-ai-governance

uv run python scripts/seed_canonical_demo.py --json
```

The harness reads `agent_id` from:

```text
artifacts/demo/canonical-seed-manifest.json
```

You can also pass `--agent-id` explicitly.

Before running P1.6d, the canonical Agent must be restored (`kill_switch_engaged=false`)
and its Runtime Control projection must be healthy.

## Start the live services

Start Redis and all dependencies required by your local Governance deployment. Start
the real Router on `127.0.0.1:8082`.

Start Governance on `127.0.0.1:8000` with its Router base URL pointing to the barrier:

```env
POLICY_MODEL_ROUTER_BASE_URL=http://127.0.0.1:18082
```

Do **not** start anything on port `18082`; the verification harness owns that port.

The harness starts and stops the Credit Desk A2A server itself.

## Run

From the Governance repository:

```bash
uv run python scripts/verify_p1_6_cross_repo_e2e.py \
  --governance-url http://127.0.0.1:8000 \
  --router-url http://127.0.0.1:8082 \
  --proxy-host 127.0.0.1 \
  --proxy-port 18082 \
  --credit-desk-repo /Users/brunovicco/Projects/multi-agent-credit-desk
```

Expected final output:

```text
[p1.6d] PASSED
[p1.6d] A=allowed, B=kill_switch_engaged, B-after-restore=runtime_authorization_revoked, C=allowed
[p1.6d] Credit Desk: deterministic decision preserved, narrative omitted
```

The evidence report is written to:

```text
artifacts/e2e/p1.6-cross-repo-live-report.json
```

It intentionally contains identifiers, versions, transition IDs and reason codes only.
It does not contain API keys, authorization signatures, prompts, customer inputs or raw
Router request bodies.

## What each step proves

### A — normal single-use authorization

Governance sees Runtime Control inactive, signs A, and the Router accepts it. Replay
protection consumes A normally.

### B — kill switch races a pre-issued authorization

Governance performs its normal pre-check and signs B. The barrier receives B and calls
the real Governance activation endpoint using B's signed `agent_version` as the
optimistic concurrency version.

The activation returns only after the monotonic Redis projection is applied. The
barrier then forwards the **exact B** to the Router.

Expected:

```text
403 kill_switch_engaged
```

Governance validates the returned `RuntimeViolation` binding and persists B as a
blocked routing decision.

### Credit Desk while active

The harness starts the real `decisao-agent` A2A server and submits a healthy
application.

Governance blocks optional model routing before a new authorization is issued.

Expected Credit Desk result:

```json
{
  "decision": "APPROVAL_RECOMMENDED",
  "narrative": null
}
```

The deterministic credit decision is preserved and no LLM completion is attempted.

### Restore + exact B

The harness deactivates Runtime Control through Governance. The restored snapshot keeps:

```text
revoked_through_agent_version = versão do Agent imediatamente antes do restore
revoked_through_agent_version >= B.subject.agent_version
```

The harness sends the exact captured B directly to the Router.

Because P1.6b evaluates Runtime Control **before replay consumption**, B was not
consumed by the earlier kill-switch denial.

Expected:

```text
403 runtime_authorization_revoked
```

A replay denial here is a test failure.

### C — fresh authorization generation

A new Governance request issues C against the incremented Agent version.

Expected:

```text
C.subject.agent_version > B.subject.agent_version
Governance outcome = allowed
```

This proves restoration does not resurrect pre-kill authorization but does permit new,
freshly governed work.

## Failure recovery

If the harness is interrupted after activation, restore the Agent through the normal
Governance Runtime Control API. Do not edit Redis manually.

If Governance is not using the barrier URL, the harness fails immediately after A
because it observes no proxied Router request.

If B returns `replay_detected`, stop: replay ordering has regressed. P1.6 requires
Runtime Control enforcement before replay consumption.

If the Router returns `runtime_control_unavailable`, verify that Governance and Router
are pointed to the same Redis database and exact key prefix.

## CI scope

P1.6d is intentionally opt-in and is not part of the default repository CI because it
requires multiple repositories and running infrastructure.

Normal CI validates the harness's bounded parsing and fail-closed behavior with:

```bash
uv run pytest apps/api/tests/test_p1_6_cross_repo_e2e_harness.py
```

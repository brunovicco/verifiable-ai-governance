# GI-3 advisory finding review boundary

- **Status:** Current
- **Owner:** Platform engineering, security and AI Governance
- **Last reviewed:** 2026-08-17
- **Review trigger:** Disposition, authorization, audit, persistence or delivery change
- **Authoritative sources:** ADR 0060 and the GI-3 application/architecture tests

GI-3 records an authorized, content-minimized review disposition for one advisory finding. It does
not approve a governed subject and exposes no delivery path.

## Guaranteed sequence

```text
GovernanceFindingEnvelope (still untrusted)
  → reconstruct through the closed current schema
  → require provenance correlation to match authenticated review context
  → authorize actor + subject + finding type through a consumer-owned port
  → hash the complete canonical envelope
  → commit one content-minimized review audit receipt
  → return a non-authoritative GovernanceFindingReviewReceipt
```

Denial occurs before audit. An audit append or commit failure withholds the receipt. Cancellation
propagates and performs best-effort rollback if an audit transaction was opened.

## Dispositions

| Disposition | Operational meaning | Explicitly not |
|---|---|---|
| `accepted_for_consideration` | Candidate may be considered by a separate governed workflow | approval, compliance or authorization |
| `rejected` | Reviewer declines this finding | rejection of the initiative/system |
| `deferred` | No conclusion is recorded | an implicit acceptance or approval |

No disposition changes initiative, assessment, control, model, agent, authorization, runtime or
evidence state.

## Authorization boundary

`GovernanceFindingReviewAuthorizerPort` receives only:

- actor ID;
- governed subject ID;
- finding type;
- administrator-access assertion.

The port must return exactly `True` to permit review. A concrete consumer must derive these facts
from authenticated identity and subject-specific policy. GI-3 deliberately provides no default
owner/admin mapping because the subject class is not yet fixed.

## Audit minimization

The `governance_intelligence.finding_reviewed` event may contain review/finding/run IDs, finding
type, schema version, candidate digest, actor/subject/correlation, administrator-access assertion,
disposition and UTC review time.

It must not contain statement, confidence, source references, source bytes, provider/model identity,
prompts, chain-of-thought, tool output, storage locations or raw responses. The candidate digest is
SHA-256 over the complete envelope serialized as sorted compact JSON.

## Failure triage

| Public failure | Check |
|---|---|
| `invalid_request` | envelope reconstruction, fixed advisory fields and correlation match |
| `forbidden` | reviewer authorization for the exact subject and finding type |
| `dependency_unavailable` before audit | authorization dependency |
| `dependency_unavailable` after authorization | audit database, append, commit or local clock/ID seam |

Do not log the finding payload while investigating. Use the content-free review/finding IDs,
correlation ID and candidate digest.

## Verify locally

```bash
uv run pytest -q \
  apps/api/tests/test_governance_intelligence_review_application.py \
  apps/api/tests/test_governance_intelligence_application.py \
  apps/api/tests/test_architecture.py
```

Run the complete repository gate before merging:

```bash
uv run python scripts/quality_gate.py
```

## Before adding persistence or delivery

1. define the concrete governed subject and reviewer authorization policy;
2. configure bounded timeout and retry behavior for any remote authorization adapter;
3. preserve the distinction between consideration and authoritative approval;
4. define request idempotency, concurrent review and supersession behavior;
5. decide whether finding content must be retained and for how long;
6. define deletion, legal hold, export and reviewer-access rules for derived content;
7. render statements as untrusted text without active markup or tool execution;
8. add rate, size and abuse limits at the delivery boundary;
9. keep provider/model execution behind the existing GI-2 boundary;
10. map accepted recommendations through separate existing governed use cases and test denial,
    replay, races, audit outage and cancellation behavior.

GI-3 has no endpoint, queue, provider, finding-content persistence, migration or replay guarantee.

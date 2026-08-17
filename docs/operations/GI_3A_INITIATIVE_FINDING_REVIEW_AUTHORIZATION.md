# GI-3A initiative finding review authorization

- **Status:** Current
- **Owner:** Platform engineering, security and AI Governance
- **Last reviewed:** 2026-08-17
- **Review trigger:** Initiative identity, ownership, administrator or review delivery change
- **Authoritative sources:** ADR 0061 and the GI-3A adapter/application/architecture tests

GI-3A supplies the first concrete authorization policy for the internal GI-3 review boundary. It
allows an initiative owner or authenticated administrator to record a non-authoritative disposition
without exposing a review endpoint or retaining finding content.

## Policy

| Condition | Decision |
|---|---|
| Existing initiative and `actor_id == business_owner_id` | Allow |
| Existing initiative and authenticated `is_admin is True` | Allow |
| Existing initiative and any other actor | Deny |
| Missing, nil, malformed, uppercase or prefixed subject ID | Deny |
| Database dependency failure | `dependency_unavailable` |

`subject_id` must be the exact lowercase, hyphenated, non-nil UUID stored as `Initiative.id`. All
current finding types use the same policy. A risk or control candidate does not confer a reviewer
role and cannot select an authoritative approval area.

## Request sequence

```text
Validated GovernanceFindingReviewAccess
  → validate canonical initiative subject identity
  → open a short-lived authorization session
  → select only Initiative.business_owner_id for the exact subject
  → allow owner/admin or deny without audit
  → close the authorization session
  → execute the existing GI-3 digest and minimized-audit transaction
  → return a non-authoritative review receipt after commit
```

The authorization read and receipt audit intentionally use separate session lifetimes. No
initiative row is locked or mutated.

## Failure and privacy rules

- do not distinguish absent initiatives from forbidden initiatives to the caller;
- do not retry authorization database failures inside the adapter;
- do not log finding statements, source references, prompts, provider/model fields or storage
  coordinates;
- do not persist a receipt after denial;
- do not treat `accepted_for_consideration` as approval, compliance or authorization;
- do not accept caller-controlled administrator assertions at a future delivery boundary.

## Verify locally

```bash
uv run pytest -q \
  apps/api/tests/test_governance_intelligence_review_authorization_adapter.py \
  apps/api/tests/test_governance_intelligence_review_application.py \
  apps/api/tests/test_architecture.py
```

Run the complete repository gate before merging:

```bash
uv run python scripts/quality_gate.py
```

GI-3A adds no endpoint, queue, provider, full finding table, migration, idempotency guarantee or
governed-state transition.

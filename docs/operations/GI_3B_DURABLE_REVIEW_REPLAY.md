# GI-3B durable advisory finding review replay

- **Status:** Current
- **Owner:** Platform engineering, security and AI Governance
- **Last reviewed:** 2026-08-17
- **Review trigger:** Request identity, receipt schema, persistence, transaction or replay change
- **Authoritative sources:** ADR 0062, migration 0021 and the GI-3B application/concurrency tests

GI-3B makes an internal advisory finding review safely repeatable across processes and database
races. It persists minimized receipt evidence, not finding content, and exposes no delivery path.

## Execution sequence

```text
request_id + finding + disposition + authenticated access
  → validate non-nil request UUID and reconstruct the closed finding schema
  → require provenance correlation to match authenticated access
  → perform current actor/subject/type authorization
  → hash the complete canonical envelope
  → load minimized receipt by request_id
     ├─ exact valid binding: return the original receipt, add no audit event
     ├─ different or corrupted binding: fail with content-free conflict
     └─ absent: insert receipt + append audit event + commit atomically
  → on unique race: roll back, reload the winner once, require exact binding
```

Current authorization always precedes durable lookup. A prior successful review does not preserve
permission after the actor's relationship to the subject changes.

## Identity and binding

| Identity | Meaning |
|---|---|
| `request_id` | Caller command identity and unique replay key |
| `review_id` | Generated immutable receipt/audit evidence identity |
| `correlation_id` | Trace identity; never an idempotency substitute |

An exact replay must match finding schema, finding ID and type, agent-run ID, canonical candidate
digest, subject, correlation, disposition, actor and administrator-access fact. The stored receipt
digest additionally binds request/review identities, receipt schema, review time and version.

## Durable minimization

`governance_finding_review_receipts` may store only:

- request, review, finding and agent-run identities;
- receipt and finding schema versions, finding type and version;
- candidate and receipt SHA-256 digests;
- subject, correlation and reviewer identities;
- disposition, administrator-access fact and UTC review time.

It must not store statement, confidence, source references or bytes, prompt, provider/model
identity, chain-of-thought, tool output, raw response, storage location or free-form rationale.
Receipt and `governance_intelligence.finding_reviewed` audit evidence commit together.

## Replay outcomes

| Condition after current authorization | Outcome |
|---|---|
| No receipt exists | Create one receipt and one audit event |
| Exact valid receipt exists | Return the original receipt; create nothing |
| Same request ID with any changed binding | `conflict` |
| Stored receipt structure or digest is invalid | `conflict` |
| Concurrent exact inserts | One winner; loser reloads and returns the winner |
| Concurrent divergent inserts | One winner; loser returns `conflict` |
| Receipt/audit dependency unavailable | `dependency_unavailable` and rollback |

Do not log the submitted finding while diagnosing a replay. Use the content-free request/review,
subject and correlation identities and digests under the normal metadata access policy.

## Verify locally

```bash
uv run pytest -q \
  apps/api/tests/test_governance_intelligence_review_application.py \
  apps/api/tests/test_governance_intelligence_review_authorization_adapter.py \
  apps/api/tests/test_migration_history.py \
  apps/api/tests/test_architecture.py
```

Run the PostgreSQL concurrency proof against a dedicated disposable database only:

```bash
POSTGRES_TEST_DATABASE_URL='<isolated asyncpg database URL>' \
  uv run pytest -q \
  apps/api/tests/test_governance_intelligence_review_concurrency_postgres.py
```

Then run the complete repository gate:

```bash
uv run python scripts/quality_gate.py
```

GI-3B adds no endpoint, review listing, queue, provider, full finding table, supersession rule or
governed-state transition. Delivery remains blocked on the follow-up controls in ADR 0062.

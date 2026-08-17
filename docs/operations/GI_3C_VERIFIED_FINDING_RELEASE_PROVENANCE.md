# GI-3C verified finding release provenance

- **Status:** Current
- **Owner:** Platform engineering, security and AI Governance
- **Last reviewed:** 2026-08-17
- **Review trigger:** Release schema, digest, transaction, retention, review or delivery change
- **Authoritative sources:** ADR 0063, migration 0022 and GI-3C application/concurrency tests

GI-3C proves that a finding presented for review passed the governed GI-2 release boundary. It
persists only content-minimized provenance inside the trusted database and adds no endpoint,
provider, queue, finding-content store or governance authority.

## Guaranteed boundary

```text
validated GI-2 envelope set
  → calculate the shared canonical complete-envelope SHA-256 digest
  → create one sealed minimized release record per finding
  → atomically insert the complete release set + append analysis_completed
  → commit before returning any envelope

GI-3 review or replay
  → reconstruct envelope and match correlation
  → perform current subject authorization
  → calculate the same canonical digest
  → load by globally unique finding_id and validate the stored release digest
  → require exact schema/finding/type/run/digest/subject/correlation binding
  → only then load or create a review receipt
```

Authorization precedes release lookup, so denial does not become a finding-existence oracle. Exact
review replay repeats release verification; neither a prior receipt nor a release row is a bearer
capability.

## Durable minimization

`governance_intelligence_finding_releases` may store only release/finding/run identities, release
and finding schema versions, finding type, candidate digest, subject/correlation identities, UTC
release time, release digest and record version. `finding_id` is globally unique.

The table and completion audit must not store statement, confidence, source references or bytes,
provider/model identity, prompts, chain-of-thought, tool output, raw responses, storage locations
or free-form rationale. The portable Governance Finding `1.0` and review receipt `1.0` contracts are
unchanged.

## Failure triage

| Condition | Outcome and check |
|---|---|
| Duplicate finding ID during GI-2 | `output_rejected`; investigate provider identity generation or concurrent/replayed analysis |
| Release insert, audit append or commit failure | `dependency_unavailable`; no envelope is returned and the transaction rolls back |
| Release absent or exact facts differ during GI-3 | `invalid_request`; no receipt lookup or write occurs |
| Release structure or digest is corrupt | `dependency_unavailable`; preserve the row and audit evidence for investigation |
| Release database unavailable | `dependency_unavailable`; do not bypass or trust a prior receipt |

Use only release/finding/run IDs, subject/correlation, timestamps and digests in diagnostics. Never
log the submitted finding or source content. Treat unexpected collisions or digest failures as an
integrity incident until explained.

## Migration and operations

Apply Alembic migration `0022` before deploying code that produces or reviews findings. Backups,
restores, retention, deletion, legal hold and export must keep release rows aligned with review
receipts and hash-chained audit evidence. Do not manually rewrite or recreate a missing release.

The release digest detects inconsistent stored facts inside the governed persistence boundary; it
is not a portable signature. If releases cross that boundary, define key custody, rotation,
revocation and signed-attestation verification in a separate reviewed decision.

## Verify locally

```bash
uv run pytest -q \
  apps/api/tests/test_governance_intelligence_application.py \
  apps/api/tests/test_governance_intelligence_release_persistence.py \
  apps/api/tests/test_governance_intelligence_review_application.py \
  apps/api/tests/test_governance_intelligence_review_authorization_adapter.py \
  apps/api/tests/test_migration_history.py \
  apps/api/tests/test_architecture.py
```

Run the dedicated PostgreSQL race proofs only against a disposable database:

```bash
POSTGRES_TEST_DATABASE_URL='<isolated asyncpg database URL>' \
  uv run pytest -q \
  apps/api/tests/test_governance_intelligence_release_concurrency_postgres.py \
  apps/api/tests/test_governance_intelligence_review_concurrency_postgres.py
```

Then run the complete repository gate:

```bash
uv run python scripts/quality_gate.py
```

Before delivery, preserve this ordering, add authenticated identity and abuse controls, define
coordinated retention, and route any accepted recommendation through a separate authoritative
governed use case.

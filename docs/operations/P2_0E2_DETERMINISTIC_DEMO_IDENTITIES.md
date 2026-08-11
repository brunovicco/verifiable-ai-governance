# P2.0e.2 - Deterministic canonical demo identities

## Purpose

P2.0e.2 makes the canonical demo reproducible across empty databases by assigning
stable UUIDv5 identifiers to its semantic business entities. It does not rebuild
release evidence; that remains P2.0e.3.

## Stable top-level identities

| Entity | Canonical ID |
| --- | --- |
| Initiative | `e3095057-9408-561b-a755-cfc9f1453af5` |
| AI system | `eabfd874-b6ca-5319-b7e1-30cae5d798df` |
| Approved model | `9a798288-ea72-5e4d-ac33-dfc7533d80cb` |
| Out-of-scope model | `150df55c-7ca6-551b-826d-545ccbe1dff5` |
| Agent | `565aa2b9-ead9-59e6-89a9-18920cced7ce` |

Routing-decision and incident identifiers remain on their existing deterministic
UUIDv5 path.

## Safe validation

Run the targeted tests first:

```bash
uv run pytest apps/api/tests/test_canonical_demo_seed.py
```

Then run repository quality gates:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy \
  apps/api/src \
  packages/governance-schemas/src \
  packages/policy-engine/src
uv run python scripts/quality_gate.py
git diff --check
```

The targeted suite includes a guarded reset/reseed test against the test database.
It verifies that the complete set of canonical business-row IDs is identical
before and after the reset.

## Validate a dedicated demo database

First seed or validate normally:

```bash
make seed-demo
make seed-demo-check
```

Inspect the generated manifest:

```bash
cat artifacts/demo/canonical-seed-manifest.json
```

The top-level IDs must match the table above.

### Explicit reset/reseed

Only on a disposable, non-production demo database, use the existing guarded
reset mechanism documented by the canonical seed. Never use this as a general
database cleanup operation.

After an explicitly authorized reset/reseed, regenerate the manifest and compare
its IDs with the previous manifest. Entity timestamps and other runtime evidence
may differ; the identity contract is what P2.0e.2 guarantees.

## Existing canonical databases

P2.0e.2 does not rewrite IDs in an already populated database. If the complete
canonical scenario was seeded before this change, `make seed-demo-check` continues
to validate that scenario with its historical generated IDs.

Do not mutate primary keys in place. When stable canonical IDs are required for a
dedicated demo environment, use the existing guarded full reset and reseed only
after confirming that the database is disposable and non-production.

## Scope boundary

Included in P2.0e.2:

- deterministic canonical business identities;
- reset/reseed identity regression tests;
- fail-closed compatibility with the existing canonical seed;
- ADR and operator guidance.

Deferred to P2.0e.3:

- rebuilding screenshots or release manifests;
- rebuilding `0.2.0-rc2` evidence bundles;
- changing release tags or publishing a release.

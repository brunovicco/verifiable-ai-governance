# ADR 0050: Fresh-install migration hardening

- Status: Accepted
- Date: 2026-08-10
- Phase: P2.0e.1

## Context

Revision `0001` used `Base.metadata.create_all(bind=op.get_bind())`. That made the first
revision depend on the current ORM metadata instead of the schema that existed when `0001`
was authored.

As the application evolved, current metadata acquired tables and columns owned by later
Alembic revisions. On a completely empty PostgreSQL database, `0001` therefore created
future objects. The migration chain then reached the revision that legitimately owned one of
those objects and failed with a duplicate-object error. The reproduced failure involved
`runtime_telemetry_events`, which is owned by revision `0012`.

The original `0001` in PR #1 already used dynamic ORM metadata; there is no earlier
self-contained Alembic version to restore. The initial database contract was reconstructed
from the ORM models and enum definitions at that historical commit.

## Decision drivers

- A migration is a versioned historical database contract.
- A fresh install must execute `0001 -> ... -> 0019` without external bootstrap logic.
- Databases already at `0019` must not be rebuilt or rewritten.
- The fix must not hide duplicate-object errors or weaken migration verification.
- Release validation must prove the behavior against a real, empty PostgreSQL database.

## Decision

Correct revision `0001` in place so it declares only the ten tables that belonged to the
initial governance inventory schema:

- `initiatives`
- `ai_systems`
- `model_assets`
- `agents`
- `assessments`
- `approvals`
- `evidence`
- `incidents`
- `international_processing`
- `audit_events`

The revision uses explicit `op.create_table` and `op.create_index` operations and has an
explicit dependency-safe downgrade. It does not import application models and does not call
`MetaData.create_all` or `MetaData.drop_all`.

The historical ORM used `Enum(..., native_enum=False)`. Its PostgreSQL representation was a
`VARCHAR` whose size came from the historical enum member names. Revision `0001` pins those
physical `VARCHAR` lengths directly so its DDL no longer changes when application enums or
SQLAlchemy enum behavior change.

No new Alembic revision is introduced. The head remains `0019`.

## Why modifying `0001` is acceptable here

Editing an already published migration is normally avoided because historical migration code
is expected to be immutable. This case is a corrective exception: the published code was not
historical at all. It delegated its DDL to mutable current application metadata, so its result
changed over time.

For a database whose `alembic_version` is already `0019`, Alembic will not execute `0001`
again. The change therefore does not alter or recreate an established head database. It only
repairs the path used when building a database from an empty state.

## Alternatives considered

### Add revision `0020`

Rejected. The failure occurs before the chain reaches `0020`, so a later revision cannot make
a broken fresh install reach head.

### Add a baseline/stamp path for new databases

Rejected. It would create a second schema-bootstrap mechanism, weaken auditability, and rely
on `stamp` or external state instead of the migration chain.

### Make later revisions tolerant of duplicate tables

Rejected. General `IF NOT EXISTS`, duplicate-table exception handling, or a special case for
`runtime_telemetry_events` would hide ownership violations rather than restore historical
revision boundaries.

### Bootstrap from a historical Git checkout

Rejected. A fresh install must be reproducible from the release being installed. It must not
require source code from an earlier commit.

## Verification

P2.0e.1 adds two complementary controls:

1. `apps/api/tests/test_migration_history.py` verifies the single linear `0001 -> ... -> 0019`
   graph, keeps `0019` as head, asserts the explicit initial-table contract, and rejects
   migration imports/calls that bootstrap schema from application ORM metadata.
2. `scripts/test_fresh_install_migrations.sh` uses a dedicated Compose definition with
   ephemeral PostgreSQL and Redis storage. It proves an empty database, runs `upgrade head`,
   verifies `0019 (head)`, runs `upgrade head` a second time, starts the API, and requires
   `/health/ready` to report database, schema, and Runtime Control readiness as `ok`.

The E2E runs as an independent CI job and can also be invoked with `make fresh-install-e2e`.

## Existing database compatibility

An existing database correctly recorded at revision `0019` requires no reset, stamp,
downgrade, or data migration. Applying this code and running `alembic upgrade head` remains a
no-op for schema revisions. Operators should verify `alembic current` before and after the
upgrade as documented in the P2.0e.1 operations guide.

## Release engineering implications

Fresh-install validation becomes a release gate rather than a manual recovery procedure.
Future migrations must remain self-contained historical contracts and may use current
`Base.metadata` as Alembic autogenerate comparison metadata only; revision upgrade/downgrade
logic must not use it as a schema bootstrap mechanism.

This phase intentionally does not regenerate release manifest, SBOM/vulnerability evidence,
provenance/attestation, or runtime benchmark evidence. Those remain coordinated P2.0e.3 work.
It also does not change canonical demo identity generation, leaving that scope to P2.0e.2.

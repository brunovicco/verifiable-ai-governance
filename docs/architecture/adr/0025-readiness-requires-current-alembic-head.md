# ADR 0025 - Readiness requires the current Alembic head

## Status

Accepted.

## Date

2026-08-06.

## Context

ADR 0009 introduced a one-shot Compose migration service and prevented the API
from starting before `alembic upgrade head` completed. P0.1 then separated process
liveness from database readiness.

A connectivity-only readiness check is still insufficient. An application may be
started outside Compose, a deployment job may reference the wrong migration
artifact, a rollback may pair old application code with a newer database, or an
operator may bypass the migration step. In each case the database can answer
`SELECT 1` while its physical contract is incompatible with the application.

The repository has already experienced this class of failure: SQLAlchemy
`create_all` left a persistent database behind the required migration while the
API process started successfully. Readiness must detect contract drift before
traffic reaches feature endpoints.

## Decision

- keep `/health/live` process-only and independent of external dependencies;
- require `/health/ready` to verify both database connectivity and migration state;
- load expected revision heads from Alembic's deployed `ScriptDirectory`;
- read current database heads through Alembic's `MigrationContext` on the same
  bounded connection used for the connectivity check;
- require exact set equality between current and expected heads;
- return HTTP `503` when the database is unavailable, the Alembic graph cannot be
  loaded, or the revision sets differ;
- do not run, stamp, repair, or infer migrations from the readiness path;
- keep revision identifiers and exception messages out of the public response;
- allow `ALEMBIC_CONFIG_PATH` for explicit deployment configuration and fail
  closed when that configured file is invalid.

Expected heads are intentionally derived rather than hard-coded. Adding a valid
migration changes the deployed revision graph, so the readiness expectation
changes with the application artifact without requiring a second revision
constant in runtime code.

## Alternatives considered

- Hard-code revision `0009` in the API: rejected because every migration would
  require a synchronized code edit and could silently drift.
- Check for a list of required tables or columns: rejected because it duplicates
  migration knowledge, does not prove the full schema state, and becomes
  increasingly incomplete.
- Continue checking only `SELECT 1`: rejected because connectivity does not prove
  compatibility.
- Run `alembic upgrade head` from readiness: rejected because health checks are
  repeated, concurrent and observational; they must not perform administrative
  writes.
- Run migrations in every API lifespan: rejected for the race, privilege and
  responsibility reasons recorded in ADR 0009.
- Accept a database ahead of the application: rejected because downgrade and
  rolling-deployment compatibility has not been established for every revision.
  Exact equality is the safe default.

## Consequences

- an API instance remains unavailable until its database matches the migration
  graph shipped with that instance;
- manual and non-Compose deployments must execute migrations before routing
  traffic;
- rolling deployments that require mixed application revisions must explicitly
  design backward-compatible expand/contract migrations rather than relying on
  readiness tolerance;
- the API image must continue shipping `alembic.ini` and the migration scripts;
- a malformed migration graph becomes a visible deployment failure;
- tests can stamp the test database dynamically from the graph rather than
  copying the current revision identifier.

## Security and privacy impact

Failing closed prevents application code from operating against an unknown data
contract, reducing the risk of incomplete authorization, audit, evidence or
incident records. The public endpoint exposes only coarse states. Logs contain
the failed check, exception type and head counts, but not database URLs,
credentials, exception messages or revision identifiers.

The runtime database identity needs read access to Alembic's version table but
does not gain DDL privileges. Migration execution remains assigned to a separate
administrative workflow.

## Operational impact

A `503` with `schema: mismatch` blocks traffic and rollout. Operators compare
`alembic current` with `alembic heads`, inspect the migration job and apply the
appropriate migration. They must not use `alembic stamp` as a generic recovery
shortcut.

Exact equality also exposes accidental rollback combinations. Deploying an older
application artifact against a newer schema remains unavailable until the
deployment follows a reviewed rollback or compatibility procedure.

## Follow-up

- add migration and readiness smoke tests to deployment pipelines;
- document expand/contract requirements before horizontal rolling deployments;
- separate migration and runtime database identities in shared environments;
- define rollback evidence for non-reversible revisions;
- add metrics for readiness failure categories without recording sensitive
  database details.

# ADR 0009 - Blocking migrations at Compose startup

## Status

Accepted.

## Date

2026-08-01.

## Context

The local environment used `AUTO_CREATE_SCHEMA=true` in the API process. SQLAlchemy's
`create_all` creates missing tables, but does not transform existing tables. After
migration `0004` added `initiatives.current_review_round`, a persistent volume still
at `0003` remained incomplete. The API started normally and only revealed the
incompatibility when querying initiatives, returning a `500 UndefinedColumnError`.

The affected database contained one initiative, nine approvals, and one piece of
evidence. Recreating the volume would have erased data and hidden the defect in the
update process.

## Decision

- add a one-shot `migrate` service to Compose that runs `alembic upgrade head` using
  the same image and configuration as the API;
- start that service only after PostgreSQL is healthy;
- start the API only once `migrate` finishes with exit code zero;
- set `AUTO_CREATE_SCHEMA=false` in Compose and in `.env.example`;
- keep `create_all` only as an explicitly opt-in local convenience, not as an upgrade
  mechanism;
- preserve volumes during updates and document that `down -v` is not an update
  procedure;
- keep manual execution via `make migrate` available when the API and database are
  started outside the full Compose flow.

## Alternatives considered

- Keep using `create_all`: rejected because it does not apply changes to existing
  objects and lets the API serve traffic against an incompatible schema.
- Delete the PostgreSQL volume: rejected because it loses data and does not
  represent a real update.
- Run Alembic in the lifespan of every API process: rejected because it mixes
  migration with serving, makes it harder to distinguish failures, and creates races
  when scaling replicas.
- Rely solely on manual execution: rejected for Compose because forgetting it would
  only be discovered at runtime.
- Run the migration in the API's `CMD`: rejected because it couples the web process
  to an administrative task and would repeat the operation on every replica.

## Consequences

- the first startup after a schema revision may take longer;
- a migration failure prevents the API from starting, making the problem visible
  before it reaches traffic;
- Compose now shows a `migrate` container that completed with a zero status;
- migrations need to remain idempotent when already applied and safe for existing
  data;
- an environment without Compose requires `make migrate` before `make dev-api`.

## Security and privacy impact

Preserving the volume avoids accidental loss of evidence and audit records. The
migration uses the database account already configured for the API in the local
environment; shared environments should separate the DDL-privileged identity from the
runtime identity. Process logs record revision and outcome, not the content of
initiatives or evidence. Backups and data transformations remain subject to the same
protection, retention, and access rules as the original database.

## Operational impact

`docker compose up --build` now builds the image, waits for PostgreSQL, runs Alembic,
and only then starts the API and portal. The operator can inspect the result with
`docker compose logs migrate`. A safe retry is done by repeating the startup after
fixing the cause; the API receives no fallback to a partial schema.

Validating this decision updated a real volume from `0003` to `0004`, preserved the
existing counts, created the projection and review history, and restored the
initiatives endpoint to `200`.

## Follow-up

- test and document full backup and restore;
- define a dedicated migration identity for shared environments;
- add an operational lock to prevent two simultaneous migration jobs outside local
  Compose;
- add a schema and endpoint smoke test to the delivery pipeline;
- define a rollback policy per revision, including non-reversible migrations.

# ADR 0020 - Transactional consistency and validity of asset reviews

## Status

Accepted.

## Date

2026-08-01.

## Context

The inventory compared `expected_version` only after loading models, agents, and
systems. Because SQLAlchemy did not issue a conditional update or lock the rows, two
concurrent commands could accept the same version. In particular, one review could
compute a digest over a scope while another transaction changed that same asset,
producing an inconsistent approved projection.

In addition, migrated agents received the `unversioned` and `unspecified` markers, but
the rules accepted any non-empty text. Expired reviews kept the historical `approved`
status without exposing a separate validity, which could lead users and future adapters
to treat an expired decision as current.

## Decision

Every mutable inventory command will first lock the `ai_system` row with
`SELECT ... FOR UPDATE OF ai_systems`. That row will be the transactional mutex for the
aggregate. System changes, and creation, update, review, and retirement of models or
agents, will follow the same lock order before validating version, owner, dependencies,
or policy.

The lock is held until commit or rollback. Thus, commands on different systems remain
independent, while operations on the same system are serialized. The second command
reloads the aggregate after the lock and rejects a stale version with a stable conflict.

The domain will explicitly reject the migration's transient markers. Validity will be
represented by `review_state`, computed as `not_reviewed`, `current`, or `expired` from
digest, deadline, and the UTC clock. The persisted status will not be rewritten by the
passage of time; the API, portal, and future enforcement points must use the computed
state for validity decisions.

## Alternatives considered

- **`version_id_col` on every entity:** would offer conditional updates, but would
  widen the change to workflows outside the inventory, which today increment versions
  explicitly and would need uniform handling for `StaleDataError`.
- **Individual lock per model and agent:** would allow more concurrency, but would
  require a global order between system, models, and agents and would be more prone to
  deadlocks during cascading invalidations.
- **A job that flips `approved` to another status on expiration:** would duplicate a
  derivable fact, introduce operational lag, and mix lifecycle with validity.
- **Accepting the migrated markers with a warning:** rejected because it would allow
  approving a scope whose actual version or region remains unknown.

## Consequences

- concurrent commands on the same system execute sequentially;
- throughput across different systems is not reduced;
- expected versions become effective for all inventory mutations;
- an agent review and a model change cannot cross the same critical window;
- consumers need to distinguish lifecycle `status` from `review_state`;
- migrated records require an explicit update before approval.

## Security and privacy impact

The lock prevents approval over a stale scope and preserves the link between digest,
decision, and current content. No new personal data is persisted. The computed state
uses metadata that already exists and does not record queries or prompt content.
Rejecting the markers keeps fail-closed behavior for incomplete provenance.

## Operational impact

There is no new database migration. PostgreSQL must support row-level locking, already
guaranteed by the adopted version. Inventory transactions must stay short and must not
make external calls while holding the lock. CI now runs a concurrency regression on
PostgreSQL 17; the local test is enabled by `POSTGRES_TEST_DATABASE_URL`.

Future metrics should observe wait time, version conflicts, and transaction duration per
system, without including sensitive identifiers in labels.

## Follow-up

- use `review_state=current` in the `policy-model-router` adapter;
- create alerts for reviews approaching expiration;
- monitor contention before considering more granular locks;
- evaluate uniform conditional versioning when other aggregates are revisited.

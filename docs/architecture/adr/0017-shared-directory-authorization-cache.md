# ADR 0017 - Shared directory authorization cache

## Status

Accepted.

## Date

2026-08-01.

## Context

Sensitive routes resolved Microsoft Graph on every request whenever the OBO integration
was enabled. This inflated latency and exposure to throttling. An in-memory-only cache
would reduce calls, but would allow diverging decisions across replicas and would not
offer a single administrative invalidation point.

Authorization cannot indefinitely reuse an association that has been removed. It also
must not turn the cache into a parallel directory holding a user's token, profile, or
group inventory.

## Decision

PostgreSQL will be the shared store for derived authorization snapshots. The key is the
stable identity `(tenant_id, object_id)`, and the persisted ID is a deterministic UUID.
Each snapshot contains only:

- effective approval areas;
- catalog ID, version, and digest;
- IDs of applied mappings and abstract source types;
- original resolution source;
- `resolved_at`, `expires_at`, `invalidated_at`, and version.

Bearer token, OBO access token, name, email/UPN, department, raw Graph response, and
group object IDs are not persisted.

The TTL comes from `DIRECTORY_AUTHORIZATION_CACHE_TTL_SECONDS`, defaulting to 60 seconds
with a bound of 5 to 300 seconds. The core reuses a snapshot only when:

1. the authenticated identity matches the key exactly;
2. `now < expires_at`;
3. the digest matches the loaded catalog;
4. no invalidation exists at or after the resolution time.

Miss, expiration, catalog change, or invalidation all require a live resolution. If the
required Graph call is unavailable, the operation fails closed. An unresolved overage is
never stored.

Writes use a native upsert. The resolution timestamp is captured before the remote call:
a refresh started before an invalidation does not overwrite it, even if Graph responds
later. A resolution that is genuinely later can publish a new snapshot; an earlier or
concurrent resolution is rejected.

The administrative endpoint
`POST /api/v1/auth/directory-authorization-cache/invalidate` accepts the target
identity, an enumerated reason, and an optional ticket reference. It removes the derived
content, keeps a shared invalidation marker, and includes a hash-chained event in the
same transaction. The audit payload uses a digest of the target, the reason, and the
reference, never the raw UUIDs. The target tenant must belong to the deployment's
trusted allowlist.

## Alternatives considered

- Local in-memory cache: rejected due to divergence across replicas and non-distributed
  invalidation.
- Redis for the MVP: deferred to avoid a new operational dependency; PostgreSQL already
  provides consistency and a joint transaction with auditing at the current volume.
- Persisting profile and groups: rejected on minimization and retention grounds, and the
  risk of creating a secondary directory.
- Using an expired snapshot during a Graph outage: rejected because availability must
  not extend the access window.
- Treating invalidation as definitive revocation: rejected. The cache controls
  freshness; IAM and Entra remain the authority over account, session, groups, and App
  Roles.

## Consequences

Authorization calls within the TTL can avoid OBO and Graph, while `/auth/me` can still
fetch the minimal profile for display. All replicas observe the same snapshot and
invalidation marker.

Migration `0005` creates a disposable table. Downgrade removes only the cache and
markers; the audit chain remains. Deployments must run the migration before bringing the
API up.

PostgreSQL now sits on the corporate authorization path. A read or commit failure
returns a safe error instead of continuing without the shared control. Reads use a short
session and release the connection before any call to Graph; the adapter does not hold a
database transaction open while waiting on a remote dependency.

## Security and privacy impact

The cache holds derived authorization and must receive the same access, backup, and
encryption controls as the database. Even without raw groups, areas and mappings are
access-control data. Operational retention may remove expired rows in the future,
without erasing audit events.

Invalidation requires `is_admin`, which under Entra mode depends on the trusted boolean
claim and is removed for guest or ambiguous accounts. References are short ticket
identifiers, not free text.

## Verification

- domain tests cover identity, digest, expiration, and invalidation;
- application tests cover unstored overage and races with invalidation;
- adapter tests cover round-trip, shared marker, and later refresh;
- HTTP test covers denial for non-administrators and audit without target UUIDs;
- the migration must pass upgrade, downgrade to `0004`, and re-upgrade on real
  PostgreSQL.

## Follow-up

- integrate the local restriction defined in ADR 0018 with future Entra session
  revocation;
- validate actual group removal, guest, Conditional Access, and SLA in a non-production
  tenant;
- export aggregated hit, miss, expiration, invalidation, and failure metrics, without
  user identifiers;
- define periodic cleanup of expired entries and a retention policy.

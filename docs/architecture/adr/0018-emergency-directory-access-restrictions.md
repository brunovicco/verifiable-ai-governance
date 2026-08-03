# ADR 0018 - Emergency restriction of Entra identity access

## Status

Accepted.

## Date

2026-08-01.

## Context

Invalidating the authorization cache forces a fresh lookup, but does not prevent an
identity that is still valid from regaining capabilities. Revoking sessions in Microsoft
Entra ID also does not directly end the session issued by the application itself, and
can take a few minutes to take effect. The platform needs a mechanism under its own
control that immediately stops all authenticated routes during offboarding, compromise,
or incident response.

The control must not depend on Graph availability, keep an in-memory-only list, reuse a
stale result, or turn the authorization cache into a source of blocking.

## Decision

PostgreSQL will hold the current restriction state per stable identity
`(tenant_id, object_id)`. The `directory_access_restrictions` table contains only the
IDs needed for the binding, a boolean state, the instant of the change, version, and
operational timestamps. History remains in the hash-chained events; name, email,
profile, token, and groups are not copied.

After authentication and before any protected route, the API queries this state in a
short session. A blocked identity receives `403`; an error, an inconsistent binding, or
an invalid state receives `503`. The query does not use a positive in-memory cache, so
all replicas observe the persisted block on the next request. Local identities, without
a directory binding, remain outside this corporate control.

Two administrative commands form the operational edge:

- `POST /api/v1/auth/directory-access/block` suspends access;
- `POST /api/v1/auth/directory-access/restore` restores access.

Both require `is_admin`, restrict the target to `OIDC_ALLOWED_TENANT_IDS`, accept an
enumerated reason and a short incident reference. The transition uses an upsert
conditioned on the instant, so as not to overwrite a more recent concurrent event.

Within the same transaction, the command:

1. changes the persisted state;
2. invalidates the identity's authorization snapshot;
3. writes an audit event with a SHA-256 digest of the target;
4. commits.

Restoring does not recover previous capabilities: the invalidation forces a current
resolution of the catalog, token, and Graph the next time an operation requires
authorization.

## Boundary with Microsoft Entra ID

This control ends access to the platform; it does not change the account in the tenant
and does not call `revokeSignInSessions`. IAM must still disable the account, remove App
Roles/groups, revoke sessions, and apply Conditional Access as the incident requires. A
future integration with those actions would be a separate adapter and would require
permissions, consent, a threat model, and validation in a non-production tenant.

Microsoft's documentation states that the application controls its own session and that
Entra does not revoke it directly. It also states that `revokeSignInSessions` invalidates
Entra refresh tokens and cookies, may have a small delay, and does not cover sessions of
external users authenticated in their home tenant.

## Consequences

- every protected Entra request adds a short PostgreSQL read;
- store unavailability blocks corporate access instead of bypassing the control;
- a blocked administrator cannot restore themselves; the operation requires another
  administrative identity, following the emergency access procedure;
- the restriction is platform-global, not limited to an approval area;
- the audit trail proves each transition without exposing the target's UUIDs in the
  payload.

## Verification

- domain tests validate UUID, digest, time, and version;
- application tests cover block, restore, tenant boundary, and atomic failure;
- adapter tests cover round-trip, concurrency, and persistent binding;
- HTTP test demonstrates that a block reaches a business route on a subsequent request;
- the migration passes upgrade, downgrade to `0005`, and re-upgrade on real PostgreSQL.

## Follow-up

- implement a separate adapter for session revocation via Microsoft Graph;
- validate disabled account, group/App Role removal, guest, and Conditional Access in a
  non-production tenant;
- add aggregated metrics for block, restore, and read failure;
- integrate alerting and the emergency access process without logging the target's
  identity.

## Official references

- [Revoke user access in an emergency](https://learn.microsoft.com/en-us/entra/identity/users/users-revoke-access)
- [`revokeSignInSessions` in Microsoft Graph](https://learn.microsoft.com/en-us/graph/api/user-revokesigninsessions?view=graph-rest-1.0)
- [Continuous Access Evaluation](https://learn.microsoft.com/en-us/entra/identity/conditional-access/concept-continuous-access-evaluation)
- [Emergency access administrative accounts](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/security-emergency-access)

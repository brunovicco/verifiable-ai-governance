# ADR 0014 - Versioned Entra authorization catalog

## Status

Accepted.

## Date

2026-08-01.

## Context

Corporate identity already validates `(tid, oid)`, and the Microsoft Graph adapter
resolves profile and transitive groups. Until this decision, values resembling
`ApprovalArea` could come directly from the configured claim. That offers no
explicit tenant-specific policy, no decision version, and no auditable mapping
identifier.

`department`, email, and group names are mutable and unsuitable for authorization.
Even trusted App Roles and object IDs need ownership, review, and explicit
association with the internal taxonomy.

## Decision

Corporate authorization now uses an immutable YAML catalog, validated at startup
and versioned as code. The catalog has a global ID and version; each mapping has
its own ID, tenant UUID, source type, value, `ApprovalArea`, state, owner, and
version.

The accepted sources are:

- `app_role`, matched exactly and case-sensitively against the Entra claim
  configured by `OIDC_ENTRA_APP_ROLES_CLAIM`;
- `group`, matched only against UUID object IDs obtained from Microsoft Graph's
  transitive memberships.

In Entra mode, claims no longer grant `ApprovalArea` directly. They only supply
App Role values to the resolver. The packaged catalog is empty and therefore
grants no capability by default. A deployment can use an external file via
`DIRECTORY_AUTHORIZATION_CATALOG_PATH`; a failed override has no fallback.

Only `/api/v1/auth/me`, approval decisions, and review-history queries use the
fully authorized principal. Routes that only need authentication do not call
Graph. App Role mappings can work without Graph; group mappings fail closed when
the transitive profile is unavailable.

A member can receive mappings. A guest only when the existing explicit policy
enables approvals; an account of unknown type never receives any. Admin remains
a separate capability, restricted to members and to the already-validated
boolean claim.

The provenance exposed to the user themself contains only the catalog, version,
semantic SHA-256 digest, mapping IDs, and source types. The approval decision
event records the same evidence in the audit chain, without raw App Roles or
group inventories.

## Alternatives considered

- Map claim values directly to `ApprovalArea`: rejected for lacking tenant,
  owner, version, or an explicit decision.
- Use `department` or display names: rejected due to mutability and collision.
- Persist the catalog in tables and build an administrative CRUD: deferred.
  Policy as code offers enough review, history, and rollback for this stage
  with a smaller attack surface.
- Grant areas from a default catalog: rejected because no real tenant or
  object ID should exist as a product default.
- Query Graph on every request: rejected to limit latency, data exposure, and
  the impact of unavailability to routes that actually depend on review
  capability.
- Record all groups and roles in the audit trail: rejected for minimization
  and the risk of creating a parallel access inventory.

## Consequences

Entra deployments need to publish a tenant-specific catalog before their users
receive approval areas. Generic OIDC and local authentication preserve the
existing mapping for testing and non-Entra integrations.

Changes are reviewable in Git, deterministically testable, and tied to the
decision by version and mapping IDs. There is no database migration in this
delivery. A file change requires a process restart to load the new policy.

The current catalog represents only the active state; history and formal
approval come from the repository and its branch-protection rules.

## Security and privacy impact

The empty default, tenant-specific matching, strict validation, canonical
UUIDs, size/count limits, opaque IDs, and duplicate blocking reduce accidental
grants. An unknown field, a boolean or textual integer, an invalid source
type, and an unknown `ApprovalArea` all prevent startup. The digest
distinguishes changed content even when someone forgets to bump the declared
version.

App Role values and object IDs are access-control data. They remain in the
token, Graph, and the protected file, but are not returned or copied into
events. Mapping IDs must be non-sensitive identifiers. `department` stays
outside authorization.

Graph or catalog unavailability does not promote the principal. Guests and
ambiguous identity remain without capabilities by default. Separation of
duties remains enforced by the review domain after area resolution.

## Operational impact

IAM, Security, and AI Governance need to define reviewers and branch
protection for the organizational file. The deployment must mount the catalog
read-only, point to the environment variable, and restart in a controlled way.
Publication must test the allowed case, the denied case, a different tenant, a
guest, and a removed group.

Immediate revocation requires a new version, publication, and restart while no
cache exists. Rollback republishes a previously approved Git revision. Metrics
must distinguish catalog failure, Graph unavailability, and a legitimately
absent mapping.

## Follow-up

- Implement a short cache, invalidation, urgent revocation, and fail-closed
  stale identity.
- Handle group overage and group claims without following URLs controlled by
  a token.
- Add bounded retry, jitter, and Graph monitoring.
- Evaluate a persisted administrative workflow when scale and segregation
  require a UI.
- Evaluate migrating global admin to its own versioned policy.

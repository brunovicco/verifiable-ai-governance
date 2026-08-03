# ADR 0016 - Entra group claims and group overage

## Status

Accepted.

## Date

2026-08-01.

## Context

The authorization catalog already accepts group object IDs obtained via Microsoft
Graph, but the identity boundary did not yet distinguish a complete `groups` claim
from a token in an overage situation. Microsoft Entra ID caps JWTs at 200 object
IDs; above that limit, it omits the list and signals that the application should
query Graph instead.

Tokens with overage can include `_claim_sources` with an endpoint. Current
documentation warns that this address can still point to the legacy Azure AD
Graph. Letting a claim determine the destination of a call would also create an
SSRF surface and bypass the fixed endpoints already defined by the adapter.

## Decision

Entra mode will have an explicit groups claim, configured via
`OIDC_ENTRA_GROUPS_CLAIM` and defaulting to `groups`. The domain will represent
three states: absent, complete, and overage.

A complete claim must be an array of up to 200 non-null UUIDs. Values are
canonicalized and duplicates removed. An invalid type, count, or object ID
rejects the token.

`hasgroups=true` or a non-empty `_claim_names.groups` signals overage. In that
state, any present `groups` list is ignored. `_claim_sources` is neither read
nor followed; the application exclusively uses the Microsoft Graph endpoints
built by the adapter.

When a trusted Graph snapshot exists, its transitive groups take precedence over
the claim. Without a snapshot, a complete claim can feed the catalog directly.
Overage without Graph uses an empty list: group mappings grant no capability,
while exact, independent App Roles continue to be evaluated.

The provenance will record only `token`, `microsoft_graph`, `none`, or
`overage_unresolved` as the resolution source. Object IDs, group counts, and
claim URLs will not be exposed or persisted in the decision event.

## Alternatives considered

- Always query Graph and ignore the complete claim: rejected as the sole
  strategy, since it increases remote dependency when the token already
  contains the complete set of object IDs.
- Follow the `_claim_sources` endpoint: rejected due to SSRF, dependency on the
  legacy Azure AD Graph, and loss of egress control.
- Accept group names or non-UUID values: rejected due to mutability and
  collision.
- Also block App Roles when overage cannot be resolved: rejected because
  signed, mapped App Roles are an independent source of authorization.
- Treat an absent `groups` claim as a complete empty group: rejected because
  absence does not prove that the tenant's configuration emitted every
  membership.

## Consequences

Deployments without Graph enrichment can resolve group-based authorization from
a complete access token. When Graph is enabled and already queried for profile
and transitive memberships, its snapshot remains the preferred source.

Clients of `/api/v1/auth/me` now receive a minimized resolution source within
the provenance. There is no database migration or persistence of the token's
object IDs.

## Security and privacy impact

The item limit, strict UUID validation, and discarding contradictory lists
prevent use of ambiguous claims. Overage does not promote access: absent Graph,
groups are evaluated as unavailable and grant no areas.

No endpoint supplied by the token influences network calls. The audit trail
contains only the abstract source and the already-approved mapping IDs, with no
membership inventory or distributed-claim data.

## Operational impact

IAM must configure `groupMembershipClaims` to emit object IDs targeted at the
API and validate scenarios both below and above 200 groups. Alerts must
distinguish `overage_unresolved` from a legitimately absent mapping.

If the organization depends on groups and users can exceed the limit, Graph OBO
must be enabled. The later shared cache is defined by ADR 0017; definitive
session and access revocation remains a separate responsibility.

## Follow-up

- Short cache with explicit freshness and cross-replica invalidation: completed
  in ADR 0017.
- Integrate the ADR 0018 emergency restriction with provider-side session
  revocation.
- Validate group overage in a non-production Entra tenant.
- Export aggregated metrics per resolution source, without group IDs.

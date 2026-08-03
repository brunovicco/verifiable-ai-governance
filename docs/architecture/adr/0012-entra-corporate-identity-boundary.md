# ADR 0012 - Corporate Entra identity by tenant and object ID

## Status

Accepted.

## Date

2026-08-01.

## Context

The existing OIDC adapter used only `sub` as the principal's identity. That claim
remains adequate for the generic contract because it is immutable and pairwise per
application, but it does not provide the stable corporate key needed to correlate
the same account across the API, Microsoft Graph, audit, and future authorization
catalogs.

In Microsoft Entra ID, `oid` identifies the object within a directory and needs to
be combined with `tid`, since a person can own distinct objects in different
tenants. The application also needs to prevent tokens from unauthorized tenants or
guest accounts from gaining approval capabilities through claim ambiguity.

## Decision

The OIDC mapping now offers two configurable modes:

- `subject`, compatible with general OIDC providers and with local Keycloak
  validation;
- `entra`, which requires `tid` and `oid` as non-null UUIDs and forms `user_id` as
  `{tenant_id}:{object_id}`.

In Entra mode:

- `OIDC_ALLOWED_TENANT_IDS` is mandatory;
- the issuer must be `https://login.microsoftonline.com/{tenant_id}/v2.0`;
- the UUID present in the issuer and in the `tid` claim must be in the allowlist;
- the optional `acct` claim classifies `0` as member and `1` as guest;
- a missing or invalid `acct` claim produces the `unknown` classification;
- a member can receive capabilities from the configured claims;
- a guest loses approval and admin areas by default;
- `unknown` always loses those capabilities;
- a guest can only receive approval areas when
  `OIDC_GUEST_APPROVALS_ENABLED=true` is explicitly set.
- admin remains exclusive to a classified member, regardless of the approval policy
  for guests.

Cryptographic validation of signature, issuer, audience, and time continues to
belong to the PyJWT adapter. The domain receives only already-verified claims and
applies identity, allowlisting, and least privilege without depending on FastAPI,
Pydantic, or Microsoft libraries.

## Alternatives considered

- Keep using only `sub`: rejected for the corporate mode because it is pairwise per
  application and is not the key used by Microsoft Graph.
- Use email, UPN, or display name: rejected because they are mutable and
  unsuitable for authorization or ownership.
- Use only `oid`: rejected because object IDs are unique only within the tenant.
- Infer guest status from email, UPN, or `idp`: rejected because it does not
  deterministically represent the object's type in the resource tenant.
- Reject any token without `acct`: rejected at this stage because `acct` is
  optional; the account can authenticate for journeys without approval, but
  remains without capabilities.
- Grant capabilities when `acct` is absent: rejected as a violation of the
  fail-closed principle.

## Consequences

Audit and ownership now receive a stable per-tenant key in Entra mode. The
`/api/v1/auth/me` endpoint also exposes tenant ID, object ID, and account
classification to the user themself.

Generic OIDC deployments continue to use `subject` with no identity change. Entra
deployments need to configure the allowlist and emit the optional `acct` claim so
members can receive approval areas.

## Security and privacy impact

Tokens from another tenant are rejected even if they have a valid signature, in
case of a misconfiguration. Invalid, missing, or null UUIDs produce no identity.
Guests and ambiguous classifications receive no privileges by default, including
admin.

Tenant ID and object ID are pseudonymous personal identifiers and can correlate
corporate activity. They are exposed only to the principal themself and used in
the necessary audit trail; bearer tokens and full group inventories remain
prohibited in logs.

## Operational impact

IAM must configure `acct` as an optional claim on the API's access token, keep the
issuer and tenant allowlist consistent, and test member, guest, missing claim, and
wrong-tenant scenarios. Changes to the allowlist or guest policy require review,
redeploy, and validation evidence. This implementation covers public Azure;
sovereign clouds will require a specific decision and configuration.

## Follow-up

- Validate real member and guest tokens against a non-production Entra tenant.
- Implement Microsoft Graph via OBO with minimal attribute selection.
- Implement a versioned catalog of App Roles and object IDs.
- Handle group overage, pagination, throttling, cache, and stale identity.
- Record the applied catalog's provenance without persisting full inventories.

# Microsoft Graph setup via On-Behalf-Of

## Scope

This runbook enables optional enrichment of `/api/v1/auth/me` with profile and
`department` data, and resolves transitive groups internally. It assumes Entra
sign-in, tenant-specific validation and the `(tid, oid)` identity are already
configured per `MICROSOFT_ENTRA_SETUP.md`.

This capability does not map groups to approval areas. `department`, email, name,
`userType` and resolved memberships are informational. None of them grant
capability.

## 1. Graph delegated permission

In the API's confidential app registration:

1. open **API permissions**;
2. add the Microsoft Graph delegated permission `User.Read`;
3. apply admin consent when the tenant's policy requires it;
4. confirm `Directory.Read.All` or any application permission was not added;
5. record the IAM owner, justification, environment and consent evidence.

The portal continues requesting only the API's delegated scope. The API uses OBO and
`https://graph.microsoft.com/.default` to receive the Graph permissions already
consented.

## 2. Confidential credential

The current implementation accepts a client secret from the API's app registration.
Create the secret with the shortest lifetime compatible with corporate policy and
deliver the value to the application via a secret manager. Do not place the value in
`.env`, a versioned Compose file, a manifest, an image, a log, an issue or a pull
request.

A certificate or workload credential is preferable for production environments, but
requires an evolution of the current adapter before that option can be enabled.

## 3. Per-environment configuration

The client ID is the Application (client) ID of the API's confidential app
registration. The tenant is taken from the already-validated `OIDC_ISSUER` and has no
separate Graph variable.

```dotenv
OIDC_ENABLED=true
OIDC_IDENTITY_MODE=entra
OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_ALLOWED_TENANT_IDS=<tenant-id>

MICROSOFT_GRAPH_ENABLED=true
MICROSOFT_GRAPH_CLIENT_ID=<api-client-id>
MICROSOFT_GRAPH_CLIENT_SECRET=<value-injected-by-secret-manager>
MICROSOFT_GRAPH_TIMEOUT_SECONDS=5
MICROSOFT_GRAPH_MAX_PAGES=20
MICROSOFT_GRAPH_MAX_ATTEMPTS=3
MICROSOFT_GRAPH_BACKOFF_BASE_SECONDS=0.25
MICROSOFT_GRAPH_MAX_RETRY_DELAY_SECONDS=2
MICROSOFT_GRAPH_MAX_RETRY_AFTER_SECONDS=300
MICROSOFT_GRAPH_MAX_RESPONSE_BYTES=1048576
```

The API fails at startup if Graph is enabled outside Entra mode, if the client ID is
not a UUID, or if the secret is missing. The login, token and Graph endpoints are
fixed to public Azure; URLs received in a token or response do not control the
destination.

## 4. Data contract

The adapter performs:

- `POST /{tenant}/oauth2/v2.0/token` with the API token as the OBO `assertion`;
- `GET https://graph.microsoft.com/v1.0/me` with a minimal `$select`;
- `GET https://graph.microsoft.com/v1.0/me/transitiveMemberOf/microsoft.graph.group`
  with `$select=id`, pagination and a local limit.

The payload returned to the user themselves has:

```json
{
  "directory_profile": {
    "display_name": "Sample Person",
    "email_or_upn": "person@example.com",
    "department": "Information Security",
    "user_type": "Member",
    "source": "microsoft_graph"
  }
}
```

Group count and object IDs stay in memory only and feed the governed catalog
described in `DIRECTORY_AUTHORIZATION_CATALOG.md`.
Bearer tokens, the secret, the full response and the full group list must not appear
in logs, traces or HTTP responses.

When the access token has a complete `groups` claim, its UUIDs can feed the catalog
without creating a call controlled by the token. If `hasgroups=true` or
`_claim_names.groups` indicates overage, the token's list is considered incomplete
and the snapshot obtained from the fixed Graph endpoint takes precedence.
`_claim_sources` is ignored, including when it points to legacy Azure AD Graph or an
unexpected host.

## 5. Validation in a non-production tenant

1. enable the variables in the test environment;
2. authenticate a member who has a `department` and a known nested group;
3. call `/api/v1/auth/me` and validate name, email/UPN, `department` and
   `userType`;
4. confirm via a controlled adapter test that the nested group is resolved, without
   exposing count or object IDs to the portal;
5. temporarily remove consent and confirm a `503` response, with no token or Graph
   details;
6. simulate an invalid secret and confirm safe behavior;
7. test a guest user and ensure the enrichment does not grant approval;
8. review logs, traces and the error tracker for tokens, the secret, the Graph body,
   UPN and full group IDs;
9. record test evidence, tenant, app registration, permission and date, without
   copying credentials or tokens.

Real Conditional Access validation may require interaction and is not replaced by
the adapter's deterministic tests.

## 6. Rotation, revocation and failures

- create a second credential before revoking the current one;
- update the secret manager, restart the deployment and validate OBO;
- revoke the previous credential and record evidence of the rotation;
- on compromise, revoke secret, sessions and consents per the IAM playbook, then
  review logs without copying secret material;
- Graph reads with `429`, `500`, `502`, `503` or `504` use at most
  `MICROSOFT_GRAPH_MAX_ATTEMPTS`, counting the first attempt;
- a numeric `Retry-After` is used when it does not exceed
  `MICROSOFT_GRAPH_MAX_RETRY_DELAY_SECONDS`; larger values fail fast and are
  propagated to the caller up to the `MICROSOFT_GRAPH_MAX_RETRY_AFTER_SECONDS`
  limit;
- without `Retry-After`, the delay uses exponential backoff starting from
  `MICROSOFT_GRAPH_BACKOFF_BASE_SECONDS`, with jitter and a local cap;
- the OBO exchange is not retried automatically, since retry is restricted to the
  idempotent profile and group reads;
- the `microsoft_graph_retry`, `microsoft_graph_retry_deferred` and
  `microsoft_graph_retry_exhausted` logs allow alerting by operation, status and
  attempt, without URL, token, user, tenant or response content;
- derived authorization decisions are stored in PostgreSQL for
  `DIRECTORY_AUTHORIZATION_CACHE_TTL_SECONDS`, between 5 and 300 seconds;
- an expired or invalidated snapshot, or one bound to a different catalog digest, is
  never reused; Graph unavailability after a miss fails closed;
- `POST /api/v1/auth/directory-authorization-cache/invalidate` requires an
  administrator, uses an enumerated reason, is visible across all replicas and
  records minimized audit evidence;
- `POST /api/v1/auth/directory-access/block` immediately contains the identity on
  the platform and coordinates state, invalidation and audit in one transaction;
- cache invalidation only forces revalidation. Incidents still require revoking the
  account, session, consent, App Role or group in Entra as appropriate;
- unavailability or an inconsistent response fails closed and never adds approval
  capabilities.

## Official references

- [OAuth 2.0 On-Behalf-Of](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow)
- [`.default` scope](https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc#the-default-scope)
- [Get the signed-in user](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0)
- [User's transitive memberships](https://learn.microsoft.com/en-us/graph/api/user-list-transitivememberof?view=graph-rest-1.0)
- [Throttling in Microsoft Graph](https://learn.microsoft.com/en-us/graph/throttling)
- [Revoke user access in an emergency](https://learn.microsoft.com/en-us/entra/identity/users/users-revoke-access)
- [`revokeSignInSessions`](https://learn.microsoft.com/en-us/graph/api/user-revokesigninsessions?view=graph-rest-1.0)

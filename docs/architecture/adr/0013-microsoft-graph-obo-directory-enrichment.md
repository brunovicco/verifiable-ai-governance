# ADR 0013 - Identity enrichment with Microsoft Graph via OBO

## Status

Accepted.

## Date

2026-08-01.

## Context

The API already validates access tokens targeted at its own audience and forms the
stable corporate identity via `(tid, oid)`. The portal also needs to display name
and organizational area without asking the user to enter them manually. The future
authorization catalog will need to receive transitive group object IDs, without
trusting group names or the `department` free-text field.

The access token sent by the portal was issued for the API and cannot be reused
directly against Microsoft Graph. The integration adds a confidential credential,
personal-data handling, and a new network dependency in the identity path.

## Decision

The application defines the async port `CorporateDirectoryPort` and the
`ResolveCorporateDirectory` use case. The Microsoft adapter implements OAuth 2.0
On-Behalf-Of (OBO): it exchanges the API's validated token for a delegated token
targeted at Graph using the `https://graph.microsoft.com/.default` scope.

The adapter:

- uses a tenant-specific token endpoint derived only from the configured tenant,
  which is already validated by the Entra boundary;
- calls the fixed public-Azure endpoints `GET /v1.0/me` and
  `GET /v1.0/me/transitiveMemberOf/microsoft.graph.group`;
- requests from `/me` only `id`, `displayName`, `mail`, `userPrincipalName`,
  `department`, and `userType`;
- collects only the `id` of groups and deduplicates values in memory;
- uses bounded pagination and follows `@odata.nextLink` only while the scheme,
  host, and path remain within the allowed Graph collection;
- applies an explicit timeout, does not follow redirects, and converts invalid
  responses, network failures, and throttling into typed errors with no remote
  content;
- caps the numeric `Retry-After` before forwarding it to the client;
- verifies the tenant before the exchange and the returned object ID before
  querying groups;
- reads responses as a stream with a configurable byte limit.

The integration is opt-in per environment. When disabled, `/api/v1/auth/me` keeps
its previous behavior and returns `directory_profile=null`. When enabled, the
endpoint includes only a minimal profile, `department`, and user type. The count
and list of object IDs are not exposed to the portal and, at this stage, do not
change `ApprovalArea`, admin, or any authorization decision.

## Alternatives considered

- Call Graph directly from the portal: rejected because it would widen
  permissions and data exposure in the browser and duplicate trust rules on the
  client.
- Forward the API-targeted token to Graph: rejected for violating audience
  separation and the supported delegated flow.
- Infer area from `department` or group name: rejected because they are mutable,
  textual, and ungoverned values for authorization.
- Use only the token's group claims: deferred to the group-overage-and-cache
  stage; it does not replace consistent transitive resolution or the versioned
  catalog.
- Add the Microsoft Graph SDK or MSAL to the core: rejected at this stage. The
  HTTP OBO contract is small and stays isolated in the adapter, preserving a
  vendor-neutral, async core.
- Persist the profile and groups on first access: deferred until a cache,
  retention, revocation, and stale-identity audit policy exists.

## Consequences

The endpoint automatically identifies name, email/UPN, and department when Graph
is enabled. The next catalog can consume already-normalized transitive object
IDs, but must remain the sole mapping source for approval areas.

Each enriched read of `/auth/me` performs an OBO exchange and Graph calls. Cache,
retry with jitter, and invalidation are not part of this delivery; unavailability
results in a safe failure and does not promote privileges.

`httpx` becomes a runtime dependency of the API to keep the adapter async and
testable with an injectable transport.

## Security and privacy impact

The confidential client's secret comes from the environment and is excluded from
the configuration representation. In production, it must be injected via a
secrets manager. Bearer tokens, the secret, full Graph responses, and group
inventories are not persisted, returned to the portal, or included in error
messages.

Strict destination validation reduces SSRF risk from response-controlled
pagination. Missing, null, or malformed UUIDs, divergent identity, remote body
beyond the limit, and excessive pagination fail closed. `department` is
organizational personal data and remains informational, granting no
authorization.

Handling must appear in the privacy inventory, in the RIPD when applicable, and
in the deployment's international-processing analysis.

## Operational impact

IAM must grant the API's app registration the minimal delegated Graph
permission, configure the confidential credential, and apply the consent
required by the organization. Deployments need to set `MICROSOFT_GRAPH_ENABLED`,
client ID, secret, timeout, and limits. The secret must be rotated without a
commit, and rotation must be tested in a non-production environment.

This implementation supports only public-Azure endpoints and client-secret
authentication. Certificates, managed identity, and sovereign clouds require an
additional adapter or decision.

## Follow-up

- Validate OBO, consent, and Conditional Access against a real Entra tenant.
- Implement a versioned App Role/object ID catalog for `ApprovalArea`.
- Handle group overage using only application-built Graph endpoints.
- Add a short cache, revocation, fail-closed stale identity, and minimized
  audit.
- Implement bounded retry with jitter and latency/failure/throttling metrics.
- Replace the client secret with a certificate or workload credential when the
  deployment environment supports it.

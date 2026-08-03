# ADR 0011 - SPA authentication with Microsoft Entra ID and MSAL

## Status

Accepted.

## Date

2026-08-01.

## Context

The Next.js portal consists of client pages that call the FastAPI API directly.
Until this decision, every call used explicit development headers to simulate
identity and areas. Those headers are appropriate only for the local Compose setup
and cannot cross the trust boundary of a shared environment.

The API already works as an OIDC resource server and validates signature, issuer,
audience, expiration, and subject. What the portal lacked was a way to obtain an
access token targeted at the API without collecting a password, persisting a client
secret, or letting the user type in their own identity.

## Decision

The corporate portal will be registered in Entra as a public Single-Page Application
and will use `@azure/msal-browser` and `@azure/msal-react`. MSAL will run
Authorization Code with PKCE and request the delegated scope exposed by the API's
app registration.

The implementation adopts:

- an authority built exclusively as tenant-specific, at
  `https://login.microsoftonline.com/{tenant_id}`;
- client ID, tenant ID, auth mode, and delegated scope as public build configuration;
- redirect and post-logout redirect restricted to the portal's current origin;
- MSAL cache in `sessionStorage`, with no `localStorage` or additional cookie;
- PII logging disabled and the platform broker disabled in this web implementation;
- silent acquisition before any interactive fallback;
- an interactive redirect when Entra or Conditional Access requires
  reauthentication;
- sending the access token only via `Authorization: Bearer` to the API;
- `credentials: omit` on the portal's calls;
- defensive removal of `X-User-Id` and `X-User-Areas` in Entra mode;
- simulated headers preserved only when `NEXT_PUBLIC_AUTH_MODE=local`.

The frontend never receives a client secret. The API remains responsible for
cryptographic validation and authorization; on-screen information or ID-token claims
do not substitute for the access token targeted at the API's audience.

## Alternatives considered

- Keep typeable headers in the corporate environment: rejected because it allows
  client-side impersonation.
- Implicit flow: rejected; Authorization Code with PKCE is the recommended flow for
  modern SPAs.
- Resource Owner Password Credentials: rejected because it collects passwords and
  does not adequately support MFA or Conditional Access.
- Store tokens in `localStorage`: rejected because it increases persistence across
  browser sessions.
- Introduce a confidential-client BFF with an HttpOnly session now: deferred. It
  reduces token exposure to JavaScript, but changes the deployment model and
  requires a server-side session and a protected credential. It may be adopted
  later if the corporate threat model requires that boundary.

## Consequences

Users in Entra mode sign in and out through the corporate provider, and decisions
no longer accept manually entered identity in the portal. Local mode remains fast
and reproducible.

`NEXT_PUBLIC_*` variables are baked into the build and are not secrets; changing
tenant, client, or scope requires a new portal build. React was upgraded from
19.2.0 to 19.2.8 to satisfy the peer version supported by MSAL React without
bypassing npm's resolution.

Since this is an SPA, access and refresh tokens are handled by MSAL's JavaScript.
The project now depends even more on XSS prevention, dependency updates, and
supply-chain review.

## Security and privacy impact

`sessionStorage` reduces persistence, but does not protect tokens against
malicious JavaScript running on the same origin. Untrusted content must not become
executable HTML; dependencies and CSP need ongoing assurance. Tokens, authorization
codes, and errors containing claims must not be logged in telemetry.

The tenant-specific authority reduces accidental authentication into another
directory. The API must remain configured with the issuer and audience of the same
tenant. Guest, App Roles, groups, and `department` still belong to later phases and
are not inferred by the UI.

The name and username shown come from MSAL's account cache and are personal data
used only for session context. The portal does not persist them at this stage.

## Operational impact

IAM must maintain separate app registrations for the portal and the API, exact
redirect URIs, the delegated scope, consent, and ownership. Changes require a
rebuild and a smoke test of login, logout, silent renewal, and Conditional Access.

An Entra configuration failure breaks the build. A silent-acquisition failure does
not degrade to local headers; it starts interaction or blocks the call.

## Follow-up

- Validate the flow against a real Entra tenant and Conditional Access policies.
- Corporate identity `(tid, oid)`, tenant allowlist, and guest policy: completed in
  ADR 0012.
- Implement OBO and minimal enrichment via Microsoft Graph.
- Create a versioned catalog of App Roles/object IDs for `ApprovalArea`.
- Define a CSP compatible with Next.js/MSAL and run XSS tests.
- Evaluate a BFF with an HttpOnly session if the production threat model requires
  it.

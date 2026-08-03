# Microsoft Entra ID setup for the portal

## Scope

This runbook configures interactive portal sign-in and access token issuance for the
API. Microsoft Graph, OBO, transitive groups and `department` are configured
separately in `MICROSOFT_GRAPH_OBO_SETUP.md`.

Use two app registrations. The portal is a public client SPA with no secret. The API
is a separate resource server and keeps validating every token itself.

## 1. API app registration

1. Create a single-tenant registration for the governance API.
2. Under **Expose an API**, define an Application ID URI approved by the
   organization.
3. Expose a delegated scope, e.g. `access_as_user`.
4. Register the IAM and platform owners.
5. Confirm access tokens are v2 and note down the client ID, tenant ID, issuer,
   audience and JWKS endpoint from the tenant's official metadata.
6. Under **Token configuration**, add the optional `acct` claim to the API's access
   token. Value `0` classifies a member and `1` classifies a guest.

Reference API configuration:

```dotenv
APP_ENV=production
DEV_AUTH_ENABLED=false
OIDC_ENABLED=true
OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_JWKS_URL=https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys
OIDC_AUDIENCE=<api-client-id>
OIDC_ALGORITHMS=RS256
OIDC_IDENTITY_MODE=entra
OIDC_ALLOWED_TENANT_IDS=<tenant-id>
OIDC_GUEST_APPROVALS_ENABLED=false
```

Do not derive issuer, audience or JWKS from received claims. Confirm the values
against the tenant's `openid-configuration` document before deploying. Entra mode
only accepts a tenant-specific v2 issuer from public Azure and requires the same UUID
to be on the allowlist.

## 2. Portal app registration

1. Create a separate single-tenant registration.
2. Under **Authentication**, add the **Single-page application** platform.
3. Register exact redirect URIs, e.g. `http://localhost:3000` for development and the
   corporate HTTPS origin for production.
4. Do not create a client secret for the portal.
5. Under **API permissions**, add the API's delegated scope.
6. Apply admin consent when organizational policy requires it.
7. Disable implicit access token and ID token flows.

## 3. Portal build

These settings are public and embedded in the bundle. They must not contain
secrets:

```dotenv
NEXT_PUBLIC_AUTH_MODE=entra
NEXT_PUBLIC_ENTRA_CLIENT_ID=<portal-client-id>
NEXT_PUBLIC_ENTRA_TENANT_ID=<tenant-id>
NEXT_PUBLIC_ENTRA_API_SCOPE=api://<api-client-id>/access_as_user
NEXT_PUBLIC_API_URL=https://api-governance.example.com
```

IDs must be explicit UUIDs and the scope must start with `api://` or `https://`.
Missing or invalid configuration stops the build. Changes require a rebuild; only
swapping environment variables in an already-built container does not change the
`NEXT_PUBLIC_*` values.

The API's CORS must accept only the portal's exact origin. Since the portal uses a
bearer token and `credentials: omit`, cookies are not needed in this integration.

## 4. App Roles and authorization catalog

In Entra mode, App Roles do not become approval areas directly. Configure the
dedicated claim and publish a tenant-specific mapping in the governed catalog:

```dotenv
OIDC_ENTRA_APP_ROLES_CLAIM=roles
OIDC_ENTRA_GROUPS_CLAIM=groups
DIRECTORY_AUTHORIZATION_CATALOG_PATH=/run/governance/entra-authorization.yaml
```

The catalog links the exact App Role value or group object ID to an `ApprovalArea`
and records the mapping's ID, version and owner. See
`DIRECTORY_AUTHORIZATION_CATALOG.md`. `department`, email, display name or group text
never grant authorization. Guests lose approval and admin areas by default. If
`acct` is missing or invalid, the account is classified as `unknown` and also
receives no capabilities. Enabling `OIDC_GUEST_APPROVALS_ENABLED=true` requires a
formal risk decision; this option grants nothing to `unknown` accounts and does not
grant admin to a guest.

The `groups` claim must contain only UUID object IDs. The API accepts at most 200
items, the documented JWT limit. The presence of `hasgroups=true` or
`_claim_names.groups` marks overage: any partial list is discarded, and when Graph is
enabled, the transitive memberships resolved via OBO take precedence. The API never
reads or follows endpoints present in `_claim_sources`.

## 5. Validation

Run in a non-production environment:

1. access the portal and confirm the tenant-specific redirect;
2. complete MFA/Conditional Access when required;
3. verify `/api/v1/auth/me` responds with `tenant_id`, `object_id`, `account_type`
   and the composite key in `user_id`;
4. confirm the absence of `X-User-Id` and `X-User-Areas` in browser requests;
5. confirm `Authorization: Bearer` targeted at the API's audience;
6. test an expired token, logout, re-authentication and tab closing;
7. test a user with no App Role and confirm they cannot approve;
8. test a guest and a token without `acct`, confirming no approval capabilities;
9. test `tid` outside the allowlist, wrong issuer or audience, and confirm
   rejection;
10. review logs and confirm token, code, full claims and PII do not appear.

The default cache is `sessionStorage`. Closing the tab ends that cache, although the
Entra browser session may still allow new SSO per corporate policy.

## 6. Rotation, revocation and incident

- Rotate the API confidential client's credential per
  `MICROSOFT_GRAPH_OBO_SETUP.md`; the portal SPA has no secret.
- Remove old redirect URIs immediately after migration.
- Block the identity on the platform first, per
  `DIRECTORY_ACCESS_INCIDENT_RESPONSE.md`, then coordinate account, sessions and
  consents in Entra.
- Publish a new build if client ID, tenant or scope changes.
- Treat suspected XSS as potential exposure of the current session's tokens.
- Log minimized failures and correlation IDs, never the tokens themselves.

## Official references

- [Authorization Code with PKCE](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [MSAL React](https://learn.microsoft.com/en-us/entra/msal/javascript/react/getting-started)
- [Token for Web API in SPA](https://learn.microsoft.com/en-us/entra/identity-platform/scenario-spa-acquire-token)
- [Token acquisition and renewal](https://learn.microsoft.com/en-us/entra/msal/javascript/browser/token-lifetimes)
- [MSAL cache configuration](https://learn.microsoft.com/en-us/entra/msal/javascript/browser/configuration)
- [Access token claims](https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference)
- [Optional claims, including acct](https://learn.microsoft.com/en-us/entra/identity-platform/optional-claims-reference)
- [Revoke user access in an emergency](https://learn.microsoft.com/en-us/entra/identity/users/users-revoke-access)

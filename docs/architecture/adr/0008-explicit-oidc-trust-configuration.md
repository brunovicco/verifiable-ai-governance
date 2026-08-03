# ADR 0008 - Explicit OIDC trust configuration

- Status: accepted
- Date: 2026-08-01

## Context

The API needs to validate access tokens from different OIDC providers without
assuming a vendor-specific JWKS URL. The previous implementation derived a
non-standard route from the issuer, fetched keys synchronously on the event loop, and
converted any truthy value of the admin claim into a privilege. It also lacked
integrated validation against a real, reproducible provider.

## Decision

- separate identity, the authentication use case, the OIDC verifier, and the HTTP
  transport;
- require explicit issuer, audience, JWKS URL, and an allowlist of asymmetric
  algorithms;
- validate signature, `iss`, `aud`, `exp`, `iat`, and `sub`, with bounded clock skew;
- limit the bearer token size before any access to the provider;
- fetch JWKS sets with timeout and bounded cache outside the API's event loop, with no
  indefinite caching of individual keys;
- distinguish an invalid token (`401`) from provider unavailability (`503`);
- accept nested claim paths for groups and ignore unknown roles;
- grant admin only when the configured claim is the JSON boolean `true`;
- require HTTPS for issuer and JWKS outside local and test environments;
- expose `/api/v1/auth/me` to verify the current identity mapping;
- validate the contract end-to-end with a pinned Keycloak version and a locally
  imported, declaratively defined realm.

Keycloak is only the reference test provider. The runtime remains vendor-independent
because it trusts only the configured JWT/JWKS contract.

## Alternatives considered

- Derive JWKS from `issuer/.well-known/jwks.json`: rejected because that route is not
  the discovery-defined JWKS endpoint and is not portable across providers.
- Perform OIDC discovery at runtime: deferred; it reduces configuration but adds
  another remote dependency at startup and requires its own cache and
  metadata-change policy. The explicit URL makes the trust root auditable per
  environment.
- Use introspection for every request: rejected for the MVP because it increases
  latency, couples availability, and exposes the token in additional calls.
- Accept symmetric algorithms: rejected because it would share the signing secret
  with the resource server and widen the blast radius of compromise.

## Consequences

- OIDC deployments need to provide more configuration, but do not depend on provider
  URL conventions;
- key rotation is absorbed by the JWKS cache and `kid` selection;
- groups outside the governance taxonomy grant no capability;
- the identity endpoint exposes only subject, email, and capabilities already
  belonging to the caller, never the token or arbitrary claims;
- interactive portal login remains out of scope for this increment.

## Security and privacy impact

The design reduces risks of algorithm confusion, audience confusion, type-coercion
privilege escalation, and denial of service from unbounded tokens. Tokens, keys, and
claim payloads are not logged. The email returned in `/auth/me` is personal data and
must follow the same access and retention controls as HTTP logs. HTTP is allowed only
in the reproducible local environment; shared environments fail at startup without
TLS.

## Operational impact

JWKS is an external dependency with a two-second timeout and a five-minute cache by
default. Unavailability with no usable key results in `503`, distinguishing
operational failure from an invalid credential without revealing details to the
client. Changes to issuer, audience, claims, or endpoint require reconfiguring the
process, consistent with Twelve-Factor. The OIDC compose file is optional and does
not change the default local path.

## Follow-up

- implement authorization code with PKCE and a secure portal session;
- test real key rotation and behavior during prolonged unavailability;
- integrate a secrets manager and organizational certificate/egress policy;
- evaluate configurable discovery if multiple providers justify the cost;
- automate Keycloak validation in CI with port isolation.

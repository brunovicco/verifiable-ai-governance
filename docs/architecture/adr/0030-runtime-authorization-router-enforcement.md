# ADR 0030 - Enforce signed Governance authorization at the model router

## Status

Accepted.

## Date

2026-08-07.

## Context

P0.4 makes approved model and agent scope re-verifiable at runtime. ADR 0028 defines the
portable runtime-authorization contract and ADR 0029 establishes Ed25519 signing, key rotation
and replay semantics.

Before P1.3, Governance still called Policy Model Router with only request fields and an API key.
The Router therefore knew who could call it, but it did not possess cryptographic proof of the
exact scope Governance had authorized for that request.

## Decision

Governance now emits a request-scoped `SignedRuntimeAuthorization` immediately before the Router
call and places it alongside the existing route request:

```json
{
  "request": { "...": "existing ModelRouteRequest v1" },
  "authorization": { "...": "SignedRuntimeAuthorization v1" }
}
```

The authorization ID is the durable Governance routing-decision ID. The signed claims bind:

- initiative, AI system and agent IDs/versions;
- current agent review digest;
- current P0.4 runtime `scope_digest`;
- exact workflow, task and workload;
- token, latency and cost budgets;
- risk tier and data classification;
- model IDs, versions, review digests and logical routing groups;
- tool and permission allowlists;
- runtime limit, human approval points and enabled kill switch;
- Governance policy and control-catalog provenance.

The authorization is issued only after P0.4 scope evaluation succeeds. Failure to produce trusted
proof is fail-closed and recorded as `runtime_authorization_unavailable`.

## Runtime scope projection

P1.3 extends the trusted routing projection with the raw reviewed facts required by the signed
contract: agent autonomy, tools, permissions, runtime limit, human approval points, kill-switch
configuration and model semantic version.

Those values are also included in the in-flight scope digest, making a mutation during the Router
round trip observable even when the persisted review projection itself has not yet changed.

## Router group alignment

The real Policy Model Router owns a closed provider-independent vocabulary. `opinion_drafting`
maps to `reasoning-strong`.

The canonical Governance demo therefore changes its approved routing group from the synthetic
`credit-opinion-approved` name to `reasoning-strong`. The intentionally out-of-scope synthetic
fixture remains available for the deterministic denial story.

An existing seeded demo database must be explicitly reset/reseeded after this change because the
approved model's reviewed routing group is material governance scope.

## Trust provenance

Production deployment must provide exact SHA-256 values for:

- Governance policy artifact;
- Governance control catalog.

P1.3 does not invent these values or derive trust from mutable database labels. The same expected
values are configured at the Router and compared against signed provenance.

## Consequences

- API key authentication remains transport/caller authentication, not Governance authorization.
- A copied route request cannot be changed without invalidating the signed request binding.
- A Router-selected group outside the signed model allowlist is rejected before the decision is
  returned to the workload.
- Replay protection is owned by the Router consumer boundary.
- P1.4 can turn the stable denial codes into standardized violation events without changing this
  trust protocol.

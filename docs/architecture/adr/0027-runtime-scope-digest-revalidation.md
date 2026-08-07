# ADR 0027 - Revalidate approved scope digests at runtime

## Status

Accepted.

## Date

2026-08-07.

## Context

Model and agent reviews already bind material scope into a SHA-256 digest over
canonical JSON. Normal inventory updates invalidate that review and dependent agent
reviews when the model scope changes.

That protects the supported write path, but the runtime reader previously trusted the
persisted `approved_scope_digest` as long as the asset remained `approved` and the
review deadline had not expired.

A database migration defect, administrative SQL, restore error, broken persistence
adapter or future write path could therefore alter material fields without clearing
the stored review digest. The runtime could then treat changed scope as though an
independent reviewer had approved it.

This is an authorization-integrity problem, not merely a data-quality problem.

## Decision

- expose `model_scope_digest()` and `agent_scope_digest()` from the asset-review
  domain;
- derive those digests from exactly the same canonical payload used when producing a
  review decision;
- recompute current model and agent digests whenever routing scope is loaded from the
  database;
- carry only a Boolean digest-match result into the routing domain rather than
  exposing a second digest value;
- fail closed with `agent_scope_drifted` when current agent facts no longer match the
  approved digest;
- exclude drifted models from the eligible model set;
- return `model_scope_drifted` when the allowed approved model set is unusable because
  material model scope changed;
- bind digest-match Booleans into the in-flight routing-scope digest so a mutation
  between request and router response changes the fingerprint;
- reject fresh agent review when an allowed model is `approved` but its current scope
  no longer matches its review digest;
- keep normal service-driven invalidation behavior unchanged;
- do not mutate lifecycle state from the read path.

## Canonical scope

Canonical serialization remains:

- UTF-8 JSON;
- object keys sorted;
- no insignificant whitespace;
- `allow_nan=False`;
- set-like arrays sorted before serialization;
- SHA-256 over the resulting bytes.

P0.4 does not expand or contract what reviewers approve. It makes the existing review
contract executable at runtime.

## Why the runtime does not rewrite the database

A routing read detecting drift must not silently clear a review, change lifecycle
state or repair records. Read paths may run concurrently and may be served by
identities without write authority.

The runtime refuses execution and persists the routing decision with a stable reason
code. Operators then investigate the source of drift and perform an authorized
update/review cycle.

## Alternatives considered

- Trust `status=approved`: rejected because lifecycle state does not prove current
  scope is the reviewed scope.
- Trust a non-null stored digest: rejected because a digest only has meaning when
  compared with current material facts.
- Clear approval from the routing reader: rejected because a read operation should
  not perform governance-state mutations.
- Add database triggers for every material field: deferred because triggers would
  duplicate material-scope knowledge in another layer.
- Persist a second current-scope digest column: rejected for P0.4 because it is
  derived data and can be recomputed from authoritative fields.
- Sign the digest in P0.4: deferred to P1.2. Equality proves scope continuity; a
  signature will later prove authorization provenance across trust boundaries.

## Consequences

- supported updates continue to invalidate reviews immediately;
- unsupported direct mutations become non-executable even if lifecycle columns were
  not changed;
- reason codes distinguish expiration/missing review from material-scope drift;
- a fresh agent review cannot depend on a drifted model review;
- no schema migration is required;
- the external router contract does not change.

## Security and privacy impact

The comparison uses digests and material registry metadata only. No prompt, model
response, document or credential content is introduced.

Public API responses do not expose the freshly computed digest.

## Operational impact

`agent_scope_drifted` or `model_scope_drifted` should be treated as a governance
integrity incident:

1. block traffic for the affected agent/model path;
2. compare current registry facts with the last reviewed scope;
3. identify the mutation source;
4. restore intended facts or submit the changed scope for independent review;
5. verify audit and migration integrity before restoring execution.

## Follow-up

- P1.1 define the signed runtime authorization envelope;
- P1.2 sign approved authorization with Ed25519;
- propagate the approved scope digest to Policy Model Router requests;
- emit standardized violation events for digest drift;
- connect kill-switch policy to repeated or high-severity drift events.

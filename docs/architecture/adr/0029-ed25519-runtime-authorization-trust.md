# ADR 0029 - Ed25519 runtime authorization trust and key rotation

## Status

Accepted.

## Date

2026-08-07.

## Context

ADR 0028 defines the canonical runtime authorization envelope and the exact bytes that
must be signed. P0.4 establishes the runtime scope digest that the authorization binds.

The system now needs cryptographic trust that can cross process and repository
boundaries without requiring Policy Model Router or downstream workloads to read the
Governance database.

The trust mechanism must support:

- deterministic Ed25519 signatures;
- explicit issuer and audience trust;
- short authorization windows;
- key rotation without downtime;
- immediate revocation;
- replay protection;
- no private signing material in public configuration or audit events.

## Decision

### Signature implementation

Governance uses the EdDSA primitive exposed by the already-declared
`pyjwt[crypto]` dependency to sign the canonical P1.1 bytes.

The authorization remains a custom JSON envelope. It is **not** encoded as JWT/JWS.

Contract v1 accepts only 64-byte Ed25519 signatures. Other EdDSA curves are rejected.

### Key distribution

Consumers receive a versioned public key set:

```json
{
  "schema_version": "1.0",
  "generation": 3,
  "keys": [
    {
      "kid": "gov-ed25519-2026-08",
      "status": "active",
      "not_before": "2026-08-07T00:00:00Z",
      "verify_until": "2026-11-07T00:00:00Z",
      "jwk": {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": "..."
      }
    }
  ]
}
```

Only public JWK material is distributed.

The private signing key is supplied separately to Governance by a secret manager, HSM,
KMS integration or protected deployment secret.

### Key lifecycle

`active`

- may sign new authorizations;
- may verify existing authorizations.

`retiring`

- must not sign new authorizations;
- may verify already-issued authorizations until `verify_until`.

`revoked`

- must not sign;
- must not verify;
- rejection is immediate even when an authorization has not expired.

At least one active key is required in every accepted key-set generation.

### Private/public pair validation

At signer initialization Governance signs a fixed domain-separated challenge with the
configured private key and verifies it against the public JWK bound to the same `kid`.

A mismatched private key therefore fails before any runtime authorization is emitted.

### Verification order

Consumers fail closed in this order:

1. contract parsing is performed by the P1.1 Pydantic model;
2. issuer must match exactly;
3. consumer audience must be included;
4. issued-at, not-before and expiry checks must pass;
5. `kid` must exist in the trusted key set;
6. key must not be revoked;
7. issue time and verification time must be inside the trusted key window;
8. Ed25519 signature must verify over canonical protected-header + claims bytes;
9. authorization ID must be atomically consumed by replay protection.

Replay state is written only after every cryptographic and trust-boundary check succeeds.

### Replay protection

P1.2 defines a replay-guard port and includes a bounded thread-safe in-memory
implementation.

The in-memory implementation is suitable for:

- unit/integration tests;
- local development;
- a deliberately single-process consumer.

It is **not** sufficient for a horizontally scaled Policy Model Router.

P1.3 must bind the same replay-guard port to a shared atomic store such as Redis or a
database uniqueness constraint.

If replay state is unavailable or at capacity, verification fails closed.

### Clock skew

Consumer policy may allow 0–60 seconds of bounded skew.

Default is zero.

Skew never extends the key's ability to sign new authorizations.

## Security properties

- no algorithm negotiation: contract v1 is Ed25519 only;
- no fallback key lookup when `kid` is unknown;
- no public-key guessing;
- no use of a retiring key for signing;
- revoked keys stop verifying immediately;
- private/public mismatch is detected before issuance;
- replay ID is consumed only after successful signature verification;
- private key material is excluded from public key sets, logs and returned objects;
- stable error codes allow audit without parsing messages.

## Consequences

- key rotation can occur without invalidating authorizations signed by the old key
  during the bounded drain window;
- compromised keys can be revoked immediately;
- Policy Model Router can validate Governance authorization offline using only public
  trust material;
- P1.3 can add distributed replay state without changing signing semantics;
- P1.4 can emit violations using stable verification error codes.

## Rotation sequence

Normal rotation:

1. generate/provision a new Ed25519 private key securely;
2. publish its public JWK as `active`;
3. change the previous key to `retiring`;
4. distribute the new key-set generation to every verifier;
5. switch Governance signer to the new active `kid`;
6. wait at least maximum authorization TTL + maximum configured clock skew;
7. mark the old key `revoked` or remove it according to retention policy.

Compromise:

1. mark the compromised key `revoked`;
2. distribute the new key-set generation immediately;
3. stop the compromised signing source;
4. activate a replacement key;
5. treat recent authorizations signed by the compromised key as suspect evidence.

## Follow-up

- P1.3 wire verified authorization and shared replay state into Policy Model Router;
- P1.4 emit standardized violation events for signature, key, scope and replay failures;
- P1.5 propagate authorization ID and signing digest through `a2a-otel-kit`;
- P1.6 connect kill-switch decisions to high-severity runtime authorization failures.

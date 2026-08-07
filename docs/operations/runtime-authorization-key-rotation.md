# Runtime authorization key rotation

This runbook covers P1.2 Ed25519 signing keys.

## Trust material

There are two different artifacts:

- **private signing key** — Governance only, delivered by secret manager/KMS/HSM;
- **public trusted key set** — distributed to Governance and every verifier.

Never place a private key in:

- `trusted-key-set-v1.json`;
- Git;
- container images;
- audit payloads;
- runtime authorization envelopes;
- application logs.

## Normal rotation

Assume:

```text
old: gov-ed25519-2026-07
new: gov-ed25519-2026-08
```

### 1. Provision the new private key

Generate the key using the organization's approved key-management boundary.

Export only the public Ed25519 JWK for the trusted key set.

### 2. Publish a new key-set generation

```json
{
  "generation": 12,
  "keys": [
    {
      "kid": "gov-ed25519-2026-08",
      "status": "active"
    },
    {
      "kid": "gov-ed25519-2026-07",
      "status": "retiring"
    }
  ]
}
```

The real document also includes key windows and public JWK values.

### 3. Deploy public trust first

All verifiers must know the new active public key before Governance starts signing with
it.

This prevents a rotation race that would appear as `unknown_key`.

### 4. Switch the Governance signer

Configure the private key and matching `kid` for the new active key.

Signer startup validates the private/public pair with a domain-separated challenge.

A mismatch fails closed with:

```text
signing_key_mismatch
```

### 5. Drain the old key

Keep the previous key `retiring` for at least:

```text
maximum authorization TTL
+ maximum verifier clock skew
+ deployment propagation margin
```

Contract v1 has a maximum authorization TTL of 600 seconds.

### 6. Revoke/remove the old key

After the drain window, move it to `revoked`.

Keep historical public-key metadata according to audit-retention policy if verification
of archived evidence is required. Do not use historical trust requirements to keep a
compromised runtime key active.

## Emergency revocation

When compromise is suspected:

1. set the affected `kid` to `revoked`;
2. increment key-set generation;
3. distribute immediately to all consumers;
4. stop the corresponding private-key source;
5. provision an active replacement;
6. review authorizations issued during the suspected compromise window;
7. open a governance/security incident.

`revoked` is immediate. The verifier does not honor token expiry as a reason to keep a
revoked key trusted.

## Stable failure codes

| Code | Meaning |
|---|---|
| `unknown_key` | `kid` is absent from the trusted key set |
| `key_revoked` | key was explicitly revoked |
| `key_not_valid_for_issue_time` | artifact was issued outside key validity |
| `key_verification_window_closed` | verification retention window ended |
| `invalid_signature` | Ed25519 verification failed |
| `issuer_mismatch` | wrong Governance issuer |
| `audience_mismatch` | artifact was not intended for this consumer |
| `issued_in_future` | issue time exceeds bounded clock skew |
| `not_yet_valid` | authorization is not active yet |
| `expired` | authorization lifetime ended |
| `replay_detected` | authorization ID was already consumed |
| `replay_store_full` | bounded replay store cannot safely accept another ID |
| `replay_store_unavailable` | replay state could not be evaluated |

## Replay store

The included `InMemoryRuntimeAuthorizationReplayGuard` is intentionally process-local.

For production Policy Model Router deployments with more than one replica, use a shared
atomic store in P1.3.

# Runtime Authorization Contract v1

P1.1 defines the portable authorization artifact that will connect Governance to
runtime enforcement.

## Trust flow

```text
Governance registry
   |
   | recompute + validate current scope
   v
Runtime Authorization v1
   |
   | P1.2: Ed25519 signature
   v
Policy Model Router
   |
   | verified claims + selected approved model group
   v
Multi-Agent Credit Desk
```

The contract is request-scoped. It is not a login token and not a generic service
identity credential.

## Wire shape

```json
{
  "protected": {
    "typ": "application/vnd.verifiable-ai-governance.runtime-authorization+json",
    "alg": "Ed25519",
    "kid": "gov-ed25519-2026-01"
  },
  "claims": {
    "schema_version": "1.0",
    "authorization_id": "...",
    "issuer": "verifiable-ai-governance:production",
    "audience": [
      "multi-agent-credit-desk",
      "policy-model-router"
    ],
    "issued_at": "2026-08-07T13:30:00Z",
    "not_before": "2026-08-07T13:30:00Z",
    "expires_at": "2026-08-07T13:35:00Z",
    "subject": {},
    "request": {},
    "scope": {},
    "scope_digest": "...",
    "policy": {}
  },
  "signature": "base64url-ed25519-signature"
}
```

## Signed bytes

P1.2 signs only:

```json
{
  "protected": {},
  "claims": {}
}
```

with the canonical JSON function in
`governance_schemas.runtime_authorization.canonical_json_bytes()`.

The protected header is intentionally covered by the signature.

## Binding to P0.4

`claims.scope_digest` is the canonical digest of the fresh runtime authorization
scope produced by Governance.

It is distinct from:

- `subject.agent_review_digest`, which binds the agent's independently reviewed
  material scope;
- each `model.review_digest`, which binds one model review;
- `policy.policy_digest`, which identifies the governance policy artifact;
- `policy.control_catalog_digest`, which identifies the control catalog artifact.

These nested digests make the authorization explainable while `scope_digest`
provides one compact runtime continuity check.

## Money

Cost is represented as integer USD micros:

```text
USD 0.30 = 300000 micros
USD 1.00 = 1000000 micros
```

This avoids floating-point ambiguity in signed bytes.

## Consumer checklist

Before execution, a consumer must eventually verify:

1. envelope and schema;
2. signature algorithm and trusted `kid`;
3. Ed25519 signature;
4. issuer and audience;
5. current UTC validity window;
6. request binding;
7. selected model binding;
8. tool and permission boundary;
9. budget boundary;
10. replay policy;
11. current scope digest when online revalidation is available.

P1.1 implements items 1 and deterministic signing bytes. P1.2 implements
cryptographic trust and temporal/audience verification.

## Checked-in artifacts

- Python model:
  `packages/governance-schemas/src/governance_schemas/runtime_authorization.py`
- JSON Schema:
  `contracts/runtime-authorization/v1.schema.json`
- synthetic credit example:
  `contracts/runtime-authorization/examples/credit-pj-v1.json`
- validation command:
  `uv run python scripts/validate_runtime_authorization_contract.py`

The example signature is syntactically valid only. It is deliberately not a
trusted cryptographic signature.

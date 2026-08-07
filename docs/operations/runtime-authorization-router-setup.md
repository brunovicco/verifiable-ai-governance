# Governance to Policy Model Router authorization setup

P1.3 assumes P0.4, P1.1 and P1.2 are already applied to Governance.

## Governance environment

```bash
export POLICY_MODEL_ROUTER_ENABLED=true

export RUNTIME_AUTHORIZATION_ISSUER='verifiable-ai-governance:production'
export RUNTIME_AUTHORIZATION_AUDIENCE='policy-model-router,multi-agent-credit-desk'
export RUNTIME_AUTHORIZATION_LIFETIME_SECONDS=300
export RUNTIME_AUTHORIZATION_SIGNING_KID='gov-ed25519-2026-08'
export RUNTIME_AUTHORIZATION_PRIVATE_KEY_PATH='/run/secrets/runtime-authorization-private.pem'
export RUNTIME_AUTHORIZATION_TRUSTED_KEY_SET_PATH='/etc/governance/runtime-authorization-keys.json'

export RUNTIME_AUTHORIZATION_POLICY_ID='baseline-governance-policy'
export RUNTIME_AUTHORIZATION_POLICY_VERSION='1.0.0'
export RUNTIME_AUTHORIZATION_POLICY_DIGEST='<64 lowercase hex chars>'
export RUNTIME_AUTHORIZATION_CONTROL_CATALOG_ID='verifiable-ai-governance-baseline'
export RUNTIME_AUTHORIZATION_CONTROL_CATALOG_VERSION='1.0.0'
export RUNTIME_AUTHORIZATION_CONTROL_CATALOG_DIGEST='<64 lowercase hex chars>'
```

The private key must be supplied by a protected deployment secret/KMS/HSM integration and must
never be checked into Git.

## Policy provenance for a local engineering environment

For an explicit source-artifact provenance snapshot you can calculate:

```bash
shasum -a 256 packages/policy-engine/src/policy_engine/engine.py
shasum -a 256 packages/policy-engine/src/policy_engine/control_catalog.yaml
```

Use release/build artifact digests rather than source-file hashes in production when your release
pipeline produces a stronger immutable provenance identifier.

The Router must be configured with exactly the same expected digests.

## Canonical demo after P1.3

The approved logical model group is now `reasoning-strong`, matching the real Router contract for
`opinion_drafting`.

If a P0.3 canonical database was seeded before P1.3, reset only the dedicated demo database and
reseed it:

```bash
make seed-demo-reset
make seed-demo-check
```

Use the repository's documented reset confirmation. Never run destructive demo reset against a
production database.

# ADR 0003 - OIDC, versioning, and audit

- Status: accepted
- Date: 2026-07-31

## Decision

- use OIDC with validation of issuer, audience, signature, and the areas claim;
- allow header-based identity only in an explicitly enabled local environment;
- use optimistic locking via `expected_version` on workflow commands;
- keep audit events append-only with a hash of the previous event and a
  per-environment salt;
- do not store prompts, responses, or documents in the audit payload.

## Known limitations

Hash chaining makes tampering detectable, but it does not replace WORM storage,
external signing, a SIEM, or trusted timestamping. Those controls will come after the
MVP.

Trust configuration, Clean Architecture boundaries, and validation against a real
provider were detailed later in ADR 0008.

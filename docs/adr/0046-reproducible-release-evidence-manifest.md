# ADR 0046 — Reproducible Release Evidence Manifest

Status: Accepted  
Date: 2026-08-09

## Context

P1.9 closes the governed runtime-response lifecycle and P1.9e proves the complete live path across
Governance, Policy Model Router, Credit Desk, Runtime Control, and sanitized telemetry. The project
can now prove control behavior, but a reviewer still needs to reconstruct which repository commits,
lockfiles, migration head, policy/control material, and committed E2E reports belong to one release
candidate.

A release label without that provenance would be weaker than the runtime evidence the project now
produces. Mutable branch names, package versions, or human-authored release notes are insufficient to
prove the exact software/evidence set.

## Decision

P2.0a introduces a deterministic, content-addressed release evidence manifest.

The manifest pins:

- exact Git commits for `verifiable-ai-governance`, `policy-model-router`,
  `multi-agent-credit-desk`, and `a2a-otel-kit`;
- project metadata and each repository's `uv.lock` SHA-256;
- the exact Alembic head and head migration digest;
- governance policy engine, control catalog, and control crosswalk digests;
- committed P1.7, P1.8, and P1.9 live evidence SHA-256 values;
- bounded baseline metadata already contained in those reports;
- compatibility binding between the latest P1.9 evidence baseline and selected release sources,
  using exact/descendant ancestry or content-equivalent squash proof;
- one canonical self-digest over the complete manifest.

Canonicalization is explicitly named `json-sort-keys-compact-v1`. The self-digest is SHA-256 over
the manifest with `manifest_digest` removed, encoded as UTF-8 JSON with sorted keys, compact
separators, `allow_nan=false`, and no ASCII coercion.

## Git object boundary

Generation requires clean input repositories, but evidence is read from exact Git objects rather
than mutable working-tree files. Verification uses the commits declared by the manifest even when
the current checkout has advanced to a later descendant commit, such as the commit that adds the
manifest itself.

This enables the two-commit evidence pattern:

```text
implementation commit
        ↓
generate manifest pinned to implementation commit
        ↓
manifest/evidence commit
        ↓
verification still re-derives implementation objects
```

## Compatibility semantics

The latest P1.9 report currently records exact Governance and Credit Desk commits plus the runtime
`a2a-otel-kit` version. It does not record the Policy Model Router Git commit.

P2.0a therefore:

- accepts an exact selected commit when it equals the P1.9 evidence commit;
- accepts normal descendants when the evidence commit is an ancestor;
- supports reviewed squash/rebase integration by re-deriving every path changed by the original
  single-parent evidence commit and requiring the selected commit to preserve identical file bytes;
- records an `attested_paths_digest` and path count for a successful `squash_equivalent` relation;
- applies the same exact/descendant/content-equivalent rule to Credit Desk and to the resolved
  `a2a-otel-kit` evidence tag;
- pins the selected Policy Model Router commit but explicitly records that P1.9 does not attest its
  exact Git commit.

A squash merge is therefore not treated as an ancestry bypass. If any path changed by the evidence
commit differs in the selected release source, generation fails closed. The original evidence
commit object must also remain available locally so the changed-path snapshot can be re-derived.

The last point is a documented evidence limitation, not silently upgraded assurance. A future live
report may close it by recording the Router commit at execution time.

## Fail-closed behavior

Generation or verification fails when:

- a required repository or Git ref is unavailable;
- `origin` does not identify the expected GitHub repository;
- generation sees a dirty/untracked input repository;
- `pyproject.toml` or `uv.lock` is absent at the selected commit;
- Alembic has zero or multiple heads;
- required policy/control/evidence files are absent;
- an evidence report is not valid JSON;
- a P1.9 baseline is neither an ancestor nor content-equivalent to the selected source;
- a referenced evidence commit needed for squash equivalence is unavailable locally;
- the referenced `a2a-otel-kit` evidence tag is missing or neither ancestor nor content-equivalent;
- the manifest self-digest is invalid;
- any re-derived field differs from the persisted manifest.

There is no network fallback and no lookup of mutable GitHub branch state during verification.

## Security boundary

The manifest contains digests and bounded provenance metadata only. It does not contain:

- private keys;
- runtime authorization signatures;
- API keys or telemetry credentials;
- prompts, completions, or credit payloads;
- arbitrary environment variables;
- raw HTTP headers or responses.

The tooling performs read-only Git operations and never checks out, resets, cleans, commits, tags, or
pushes repository state.

## Consequences

P2.0a creates a deterministic evidence root for P2.0b SBOM/vulnerability evidence and P2.0c build
provenance/attestation. Those later stages can be added as new content-addressed entries without
changing the principle that release claims must be re-derived from immutable source/evidence.

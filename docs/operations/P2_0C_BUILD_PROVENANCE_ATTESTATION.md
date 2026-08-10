# P2.0c — Build Provenance & Artifact Attestation

## Purpose

Generate deterministic release-candidate provenance from the P2.0a and P2.0b evidence roots, then create GitHub Artifact Attestations for the resulting release subjects.

## Preconditions

The local Governance repository must be clean and the exact commits declared by P2.0a must be available in the four local repositories.

Expected release roots for the current candidate:

```text
release version: 0.2.0-rc1
P2.0a manifest digest: ba55a969f86bd032c8f1babeb61e8831c58dd364ecbf29a6a5afcbda51f4c9bc
P2.0b security bundle digest: 021d8ae90d0a7bda4b717aa65c87518eadd60b37d15e3ccd406cb37f046d7db9
```

## Local generation

Run only after committing the P2.0c implementation:

```bash
python -m scripts.generate_release_build_provenance \
  --release-version 0.2.0-rc1 \
  --governance-source-repo . \
  --policy-model-router-repo ../policy-model-router \
  --credit-desk-repo ../multi-agent-credit-desk \
  --a2a-otel-kit-repo ../a2a-otel-kit
```

The output directory is:

```text
artifacts/release/provenance/
```

Generated subjects include:

```text
sources/governance-<sha>.tar.gz
sources/policy_model_router-<sha>.tar.gz
sources/multi_agent_credit_desk-<sha>.tar.gz
sources/a2a_otel_kit-<sha>.tar.gz
release-evidence-0.2.0-rc1.tar.gz
build-recipe-0.2.0-rc1.tar.gz
release-build-provenance.json
```

`release-subjects.sha256` contains the exact SHA-256 checksums passed to GitHub Artifact Attestations.

## Local verification

```bash
python -m scripts.verify_release_build_provenance \
  --governance-source-repo . \
  --policy-model-router-repo ../policy-model-router \
  --credit-desk-repo ../multi-agent-credit-desk \
  --a2a-otel-kit-repo ../a2a-otel-kit
```

The verifier performs no network calls.

## Commit pattern

Use the same two-commit evidence pattern as P2.0a and P2.0b.

First commit the implementation. Generate the provenance from that clean state. Then commit only:

```text
artifacts/release/provenance/
```

Do not regenerate after the evidence commit unless the release roots intentionally change.

## GitHub attestation

After the P2.0c PR is merged, run:

```text
Actions
→ Release provenance attestation
→ Run workflow
→ release_version = 0.2.0-rc1
```

The workflow:

1. reads the exact component commits from the committed P2.0a manifest;
2. checks out each frozen source commit separately;
3. verifies the committed deterministic P2.0c subjects against those exact sources;
4. uploads the provenance directory as a workflow artifact;
5. uses `actions/attest@v4` with `release-subjects.sha256`;
6. uploads the generated Sigstore bundle as a separate workflow artifact;
7. verifies each attestation with GitHub CLI.

## Required GitHub Actions permissions

The workflow must retain exactly the capabilities needed for file attestations:

```yaml
permissions:
  contents: read
  id-token: write
  attestations: write
```

`artifact-metadata: write` is required by the current attestation action. Do not add `packages: write` in P2.0c.

## Attestation verification

Download the workflow artifact and run, for each subject:

```bash
gh attestation verify \
  artifacts/release/provenance/<subject> \
  -R brunovicco/verifiable-ai-governance
```

The workflow also preserves the `actions/attest` Sigstore bundle as a separate artifact for later offline verification.

To verify every subject listed in the checksum file:

```bash
while read -r digest path; do
  test -n "$digest"
  gh attestation verify "$path" -R brunovicco/verifiable-ai-governance
done < artifacts/release/provenance/release-subjects.sha256
```

## Failure modes

### Selected commit unavailable

Generation fails closed. Make the exact Git object available locally; do not silently replace it with current `main`.

### Repository identity mismatch

Confirm `remote.origin.url` for each local source repository. The generator will not accept a different repository containing a coincidentally matching tree.

### P2.0b verdict is not pass

P2.0c must not attest a release candidate whose frozen security policy verdict is failing.

### Subject digest mismatch

Treat this as evidence drift. Do not edit `release-subjects.sha256` manually. Reconcile the underlying source/evidence state first.

### GitHub attestation permission failure

Confirm repository Actions permissions support `id-token: write` and `attestations: write`. P2.0c does not require package publication permission.

## Non-goals

P2.0c does not:

- publish GitHub Releases;
- push images to GHCR;
- publish Python packages;
- create long-lived signing keys;
- claim that attestation proves an artifact is vulnerability-free;
- change P2.0a or P2.0b release inputs.

## Next step

P2.0d — Runtime Benchmark & SLO Evidence.

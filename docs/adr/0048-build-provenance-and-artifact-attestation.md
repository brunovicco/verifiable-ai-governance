# ADR 0048 — Build Provenance and Artifact Attestation

## Status

Accepted for P2.0c.

## Context

P2.0a established a deterministic release-evidence manifest for `v0.2.0-rc1` and P2.0b added content-addressed SBOM and vulnerability evidence. Those roots prove what source, dependencies, policy inputs, and security findings were selected for the release candidate, but they do not yet prove which build recipe produced distributable release artifacts or which trusted workflow identity attested those artifacts.

P2.0c must add provenance without changing the already-frozen release inputs. It must also avoid introducing repository-managed signing keys or treating an unsigned JSON document as cryptographic attestation.

## Decision

P2.0c introduces two separate evidence layers.

### 1. Deterministic repository provenance

The repository produces:

- four deterministic source archives, one for each exact P2.0a component commit;
- a deterministic release-evidence bundle containing the P2.0a manifest and complete P2.0b security evidence;
- a deterministic build-recipe bundle containing the provenance workflow, schema, generator, and verifier;
- a canonical `release-build-provenance.json` binding the upstream roots, source bindings, build recipe, and subject digests;
- a deterministic `release-subjects.sha256` file suitable for artifact-attestation subject discovery.

The provenance document has its own canonical SHA-256 digest but does not claim to be a signature.

### 2. GitHub Artifact Attestation

A manual GitHub Actions workflow first re-verifies the committed deterministic subjects against the frozen source checkouts, then uses `actions/attest@v4` with `subject-checksums` to create signed SLSA build provenance attestations for those subjects.

The workflow permissions are deliberately limited to:

```yaml
contents: read
id-token: write
attestations: write
artifact-metadata: write
```

No repository signing secret is stored. GitHub Actions OIDC is used by the attestation service to obtain the short-lived signing identity. `artifact-metadata: write` is included because it is required by the current `actions/attest@v4` contract for artifact metadata records.

## Frozen upstream roots

P2.0c must preserve the exact P2.0a and P2.0b roots. Generation fails closed if:

- the P2.0a manifest self-digest is invalid;
- the P2.0b bundle self-digest is invalid;
- P2.0b is not bound to the supplied P2.0a manifest;
- the P2.0b verdict is not `pass`;
- any P2.0a source repository identity or commit cannot be resolved locally;
- the requested release version differs from the frozen manifest.

## Source archive semantics

Source archives are created from exact Git objects with `git archive`. The resulting tar stream is gzip-compressed with a zero gzip timestamp so repeated generation from the same Git object produces the same bytes.

The generator never substitutes the mutable working tree for a selected release commit.

## Release evidence bundle

The release-evidence bundle includes only the already-committed P2.0a and P2.0b evidence tree. Tar metadata is normalized and the bundle timestamp derives from the P2.0a `source_date` rather than wall-clock generation time.

## Build recipe bundle

The build-recipe bundle contains the exact provenance workflow and deterministic generation/verification implementation used by P2.0c. It is itself one of the attested subjects.

## Separation between evidence and signature

The following are intentionally different objects:

```text
release-build-provenance.json
        !=
GitHub Artifact Attestation
```

The JSON document is deterministic evidence. The GitHub attestation is the externally verifiable signature and workflow identity binding.

This avoids self-signing semantics and avoids storing private signing keys in the repository.

## Workflow trigger

Attestation is `workflow_dispatch` only.

P2.0c does not attest every pull request or ordinary CI run. The workflow is intended for explicit release-candidate provenance generation.

## No package publication

P2.0c does not push container images or packages. Therefore it does not request `packages: write` and does not use `push-to-registry`.

OCI/GHCR publication provenance belongs to P2.0e, where the published image digest will exist as a real registry subject.

## Verification

Local verification is network-free and checks:

- P2.0a canonical digest;
- P2.0b canonical digest and release binding;
- source bindings;
- exact source archive reproducibility;
- release-evidence bundle reproducibility;
- subject hashes and sizes;
- build-recipe binding;
- checksum manifest consistency;
- P2.0c canonical provenance digest.

GitHub attestation verification is a distinct online step using:

```bash
gh attestation verify <subject> -R brunovicco/verifiable-ai-governance
```

## Security properties

P2.0c establishes:

```text
release input != build recipe != signed attestation
```

and:

```text
P2.0a manifest digest
        +
P2.0b security bundle digest
        +
exact source commits
        +
build recipe digest
        +
subject digests
        ↓
P2.0c deterministic provenance
        ↓
GitHub OIDC / Sigstore attestation
```

The workflow cannot publish packages and does not contain repository-managed signing credentials.

## Consequences

The release candidate gains independently verifiable provenance for its source/evidence artifacts while preserving publication as a later release concern.

P2.0d may now benchmark artifacts against the same frozen roots, and P2.0e may publish release assets and container images with their own final registry/release attestations.

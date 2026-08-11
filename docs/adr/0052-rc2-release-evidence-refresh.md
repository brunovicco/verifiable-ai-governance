# ADR 0052 - Coordinated 0.2.0-rc2 release evidence refresh

## Status

Accepted.

## Date

2026-08-10.

## Context

P2.0a through P2.0d established separate evidence roots for the release manifest,
SBOM and vulnerability policy, deterministic build provenance, GitHub Artifact
Attestations, and live runtime benchmark/SLO evidence.

P2.0e.1 corrected fresh-install migrations and added an isolated PostgreSQL
migration/readiness E2E. P2.0e.2 made the canonical demo identities deterministic
across reset/reseed and clean databases. Those changes invalidate the old rc1
Governance source binding and require a new release-candidate evidence chain.

Simply overwriting the rc1 JSON files is insufficient. Each evidence generator has
intentional clean-worktree boundaries, and later evidence must bind earlier
committed evidence rather than an uncommitted workspace. A release candidate also
needs a single root that an operator or verifier can use to prove that every
required evidence family belongs to the same source selection.

## Decision

P2.0e.3 rebuilds evidence for `0.2.0-rc2` as a staged, content-addressed chain.

1. Commit all P2.0e.1, P2.0e.2, and P2.0e.3 implementation/tooling changes.
2. Generate a new release manifest from that clean Governance commit.
3. Preserve the rc1 Policy Model Router, Credit Desk, and A2A OTel commit bindings;
   rc2 intentionally advances only Governance.
4. Commit the manifest before generating security evidence.
5. Generate and verify SBOM/vulnerability evidence from the exact manifest source
   commits, then commit it.
6. Regenerate build provenance from a temporary clean snapshot so the tracked rc1
   provenance directory can be replaced without weakening the existing generator's
   clean-worktree invariant; verify and commit the result.
7. Run and verify the existing live runtime benchmark/SLO evidence and commit it.
8. Execute the P2.0e.1 fresh-install E2E from a `git archive` of the exact Governance
   source commit frozen in the rc2 manifest. Persist the complete log and a
   self-digested receipt, then commit both.
9. Generate a deterministic final release-candidate index binding the manifest,
   security bundle, build provenance, runtime benchmark, clean-install evidence,
   and the stable canonical demo top-level identities.
10. Attest both the existing provenance subjects and the final release-candidate
    index through GitHub Artifact Attestations with OIDC/Sigstore.

The final index is a one-way root. Child evidence never references the final index,
avoiding a digest cycle.

## Frozen sibling component policy

P2.0e.3 is a Governance hardening release candidate, not a coordinated source
upgrade of every repository. The rc2 manifest therefore keeps these rc1 bindings:

- Policy Model Router: `0344f7410fa68fbd8a61fb5d949f5d4dcf0c9166`
- Multi-Agent Credit Desk: `b326971bbe7910bd94bd45c0cafbaa11a03f8610`
- A2A OTel Kit: `a096766fd075868704276777d847c740a17ba821`

The rc2 manifest wrapper and final evidence verifier fail closed if these commits
change. Updating any sibling component requires an explicit later decision and new
compatibility evidence.

## Clean-install evidence boundary

The release clean-install receipt is produced from the Governance commit recorded
inside the release manifest, not from whatever commit happens to be checked out
when the test is run. The coordinator archives that exact commit into a temporary
directory and invokes only the isolated P2.0e.1 test script from that archive.

The receipt binds:

- rc2 release-manifest digest;
- exact Governance source commit;
- exact P2.0e.1 script digest from that commit;
- two observed Alembic `0019 (head)` states;
- successful API readiness checks;
- full log digest and size;
- local Docker/Compose execution environment metadata.

Failed runs may preserve a diagnostic log, but they do not produce a passing
release receipt.

## Provenance refresh boundary

The existing P2.0c generator correctly refuses to create its output directory when
that directory already exists and requires a clean Governance worktree. rc1
provenance is tracked, so deleting it first would make the worktree dirty and cause
the generator to fail.

P2.0e.3 therefore adds a bounded refresh wrapper. It:

- requires the real Governance worktree to be clean;
- materializes current `HEAD` into a temporary Git repository;
- removes only the stale provenance directory in that temporary snapshot;
- invokes the existing P2.0c generator unchanged;
- replaces only `artifacts/release/provenance` in the real repository after
  successful generation;
- keeps an out-of-tree backup during replacement and restores it on copy failure.

This wrapper does not change the provenance format or weaken P2.0c verification.

## Canonical demo import boundary correction

During P2.0e.3 integration, a package-level side effect from the initial P2.0e.2
implementation was found to make every `scripts.*` module import SQLAlchemy and API
models. That would break release verification jobs designed to run with standard
Python only.

The deterministic identity contract is therefore split into a pure standard-library
module. `scripts/__init__.py` is side-effect free, while the supported canonical seed
CLI explicitly installs the SQLAlchemy listener. This preserves P2.0e.2 behavior
without coupling release tooling to application startup dependencies.

## Final candidate invariant

The final offline verifier re-derives every child evidence family and then checks
runtime equivalence between the Governance source commit frozen in the rc2 manifest
and the current candidate commit. Evidence-only commits after source freeze are
allowed. Changes under production runtime paths are rejected.

A passing index therefore means:

`source selection -> security -> provenance -> runtime benchmark -> fresh install -> final index`

all belong to one rc2 candidate and the current candidate has not changed frozen
runtime behavior.

## Alternatives considered

### One script that runs every evidence generator without commits

Rejected. It would violate the clean-worktree and immutable-upstream boundaries
that make the current evidence chain trustworthy.

### Reuse rc1 provenance and benchmark

Rejected. Their upstream source roots point to the old Governance selection.

### Run fresh-install against current HEAD

Rejected. Evidence commits occur after source freeze. Testing current HEAD would
make it ambiguous which source tree the release receipt actually attests.

### Advance all sibling repositories to their latest HEAD

Rejected. P2.0e.3 addresses Governance release hardening. Unrelated source upgrades
would enlarge compatibility scope without new cross-repository evidence.

### Tag `v0.2.0` in this phase

Rejected. P2.0e.4 remains the explicit final verification, tag, and release step.

## Consequences

- rc2 gets one deterministic release-candidate root in addition to the existing
  specialized evidence bundles.
- Fresh-install success becomes content-addressed release evidence instead of an
  operator-only terminal result.
- GitHub attestation covers the final candidate root as well as P2.0c subjects.
- Evidence generation remains intentionally staged across commits.
- No production control, authorization, runtime enforcement, or migration semantics
  are weakened by this phase.
- P2.0e.4 can make the final tag decision using one offline verifier plus the
  GitHub attestation result.

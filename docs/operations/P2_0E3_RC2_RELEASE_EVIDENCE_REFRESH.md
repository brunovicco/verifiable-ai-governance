# P2.0e.3 - 0.2.0-rc2 release evidence refresh

## Purpose

P2.0e.3 rebuilds the release evidence chain after the P2.0e.1 fresh-install fix and
P2.0e.2 deterministic canonical identities. It does not create the final `v0.2.0`
tag or GitHub Release; those remain P2.0e.4.

The required order is intentional:

```text
implementation commit
  -> rc2 manifest commit
  -> security evidence commit
  -> provenance evidence commit
  -> runtime benchmark commit
  -> frozen-source clean-install evidence commit
  -> final release-candidate index commit
  -> GitHub OIDC/Sigstore attestation
```

Do not collapse these stages into one dirty worktree. The generators intentionally
use clean-worktree boundaries so later evidence is derived from committed upstream
roots.

## Fixed rc2 sibling sources

This phase advances only Governance. The manifest wrapper pins:

```text
policy-model-router       0344f7410fa68fbd8a61fb5d949f5d4dcf0c9166
multi-agent-credit-desk   b326971bbe7910bd94bd45c0cafbaa11a03f8610
a2a-otel-kit              a096766fd075868704276777d847c740a17ba821
```

The sibling repositories must contain these commits locally. Their worktrees must
also be clean because the existing P2.0a manifest builder rejects ambiguous inputs.
The repositories do not need to have those commits checked out: the rc2 wrapper
resolves the exact pinned Git objects directly.

## Stage 0 - apply and validate P2.0e.3 tooling

Start from the branch that already contains P2.0e.1 and P2.0e.2.

```bash
cd /Users/brunovicco/Projects/verifiable-ai-governance

git status --short
git switch -c fix/p2.0e3-rc2-release-evidence

unzip -o \
  /Users/brunovicco/Downloads/verifiable-ai-governance-p2.0e3-complete.zip \
  -d /Users/brunovicco/Projects/verifiable-ai-governance
```

Validate the implementation before freezing the rc2 source:

```bash
uv run pytest \
  apps/api/tests/test_canonical_demo_seed.py \
  apps/api/tests/test_release_candidate_evidence.py \
  apps/api/tests/test_release_candidate_evidence_boundary.py

uv run ruff check .
uv run ruff format --check .
uv run mypy \
  apps/api/src \
  packages/governance-schemas/src \
  packages/policy-engine/src
uv run python scripts/quality_gate.py

git diff --check
git status --short
```

The repository-specific prohibited-import check must produce no output for the
P2.0e.3 files.

Stage all implementation/tooling files, inspect the staged scope, and commit them.
Do not include generated rc2 evidence yet.

```bash
git add \
  .github/workflows/release-provenance.yml \
  apps/api/tests/test_canonical_demo_seed.py \
  apps/api/tests/test_release_candidate_evidence.py \
  apps/api/tests/test_release_candidate_evidence_boundary.py \
  docs/adr/0051-deterministic-canonical-demo-identities.md \
  docs/adr/0052-rc2-release-evidence-refresh.md \
  docs/operations/P2_0E3_RC2_RELEASE_EVIDENCE_REFRESH.md \
  schemas/release-clean-install-evidence.schema.json \
  schemas/release-candidate-evidence-index.schema.json \
  scripts/__init__.py \
  scripts/canonical_demo_contract.py \
  scripts/canonical_demo_identity.py \
  scripts/capture_clean_install_release_evidence.py \
  scripts/generate_rc2_release_manifest.py \
  scripts/generate_release_candidate_evidence_index.py \
  scripts/refresh_release_build_provenance.py \
  scripts/release_candidate_evidence.py \
  scripts/seed_canonical_demo.py \
  scripts/verify_release_candidate_evidence_index.py

git diff --cached --check
git diff --cached --name-status
git commit -m "feat: coordinate v0.2.0-rc2 release evidence refresh"
```

Record the source commit. This is the Governance commit that the rc2 manifest must
freeze:

```bash
RC2_SOURCE_SHA="$(git rev-parse HEAD)"
printf '%s\n' "$RC2_SOURCE_SHA"
test -z "$(git status --porcelain)"
```

No production runtime path may change after this point. Evidence commits are
expected; runtime implementation changes require restarting the rc2 evidence chain.

## Stage 1 - regenerate and commit the rc2 release manifest

```bash
uv run python -m scripts.generate_rc2_release_manifest \
  --policy-model-router-repo /Users/brunovicco/Projects/policy-model-router \
  --credit-desk-repo /Users/brunovicco/Projects/multi-agent-credit-desk \
  --a2a-otel-kit-repo /Users/brunovicco/Projects/a2a-otel-kit

uv run python -m scripts.verify_release_evidence_manifest \
  --policy-model-router-repo /Users/brunovicco/Projects/policy-model-router \
  --credit-desk-repo /Users/brunovicco/Projects/multi-agent-credit-desk \
  --a2a-otel-kit-repo /Users/brunovicco/Projects/a2a-otel-kit
```

Confirm the source freeze:

```bash
python - <<'PY'
import json
from pathlib import Path

manifest = json.loads(Path("artifacts/release/release-manifest.json").read_text())
print(manifest["release"]["version"])
print(manifest["components"]["governance"]["commit"])
print(manifest["manifest_digest"])
PY
```

The version must be `0.2.0-rc2`; the Governance SHA must equal
`$RC2_SOURCE_SHA`.

Commit only the manifest:

```bash
git add artifacts/release/release-manifest.json
git diff --cached --check
git commit -m "docs: refresh v0.2.0-rc2 release manifest"
test -z "$(git status --porcelain)"
```

## Stage 2 - regenerate and commit security evidence

Required local tools remain the P2.0b toolchain: `uv`, `pip-audit`, Node/npm,
Docker, and Trivy.

```bash
uv run python -m scripts.generate_release_security_evidence \
  --policy-model-router-repo /Users/brunovicco/Projects/policy-model-router \
  --credit-desk-repo /Users/brunovicco/Projects/multi-agent-credit-desk \
  --a2a-otel-kit-repo /Users/brunovicco/Projects/a2a-otel-kit

uv run python -m scripts.verify_release_security_evidence
```

The verifier must report `verdict: pass`. Commit only the security evidence tree:

```bash
git add artifacts/release/security
git diff --cached --check
git commit -m "docs: refresh v0.2.0-rc2 security evidence"
test -z "$(git status --porcelain)"
```

Do not suppress vulnerability findings or weaken `config/release-security-policy.json`
to obtain a passing release.

## Stage 3 - safely refresh and commit P2.0c provenance

The tracked rc1 provenance directory cannot simply be removed before calling the
original P2.0c generator because that generator correctly requires a clean
worktree. Use the bounded refresh wrapper:

```bash
uv run python -m scripts.refresh_release_build_provenance \
  --policy-model-router-repo /Users/brunovicco/Projects/policy-model-router \
  --credit-desk-repo /Users/brunovicco/Projects/multi-agent-credit-desk \
  --a2a-otel-kit-repo /Users/brunovicco/Projects/a2a-otel-kit

uv run python -m scripts.verify_release_build_provenance \
  --governance-source-repo . \
  --policy-model-router-repo /Users/brunovicco/Projects/policy-model-router \
  --credit-desk-repo /Users/brunovicco/Projects/multi-agent-credit-desk \
  --a2a-otel-kit-repo /Users/brunovicco/Projects/a2a-otel-kit
```

The wrapper generates the new directory in a temporary clean Git snapshot and
replaces only `artifacts/release/provenance` after successful generation. It does
not reset or clean the real worktree.

Commit only provenance outputs:

```bash
git add -A artifacts/release/provenance
git diff --cached --check
git commit -m "docs: refresh v0.2.0-rc2 build provenance"
test -z "$(git status --porcelain)"
```

## Stage 4 - refresh runtime state, benchmark, verify, and commit

Use the existing P2.0d runtime prerequisites. Governance and Policy Model Router
must be healthy, the canonical Agent must have its kill switch inactive, telemetry
must be fresh, and Runtime Assurance must be enabled.

Before refreshing runtime evidence, fail closed if the live Router or Credit Desk
checkout is not the source frozen for rc2:

```bash
test "$(git -C /Users/brunovicco/Projects/policy-model-router rev-parse HEAD)" = \
  "0344f7410fa68fbd8a61fb5d949f5d4dcf0c9166"
test -z "$(git -C /Users/brunovicco/Projects/policy-model-router status --porcelain)"

test "$(git -C /Users/brunovicco/Projects/multi-agent-credit-desk rev-parse HEAD)" = \
  "b326971bbe7910bd94bd45c0cafbaa11a03f8610"
test -z "$(git -C /Users/brunovicco/Projects/multi-agent-credit-desk status --porcelain)"
```

If either check fails, prepare the expected source in a separate clean checkout or
worktree before continuing. Do not silently benchmark a different source selection.

Immediately before the benchmark, refresh the governed runtime evidence without
writing the tracked P1.9 report:

```bash
export P1_7_TELEMETRY_API_KEY='the-same-local-secret-configured-in-governance'

uv run python -m scripts.verify_p1_9_governed_actuation_e2e \
  --credit-desk-repo /Users/brunovicco/Projects/multi-agent-credit-desk \
  --router-url http://127.0.0.1:8082 \
  --report /tmp/p1.9-rc2-refresh.json
```

Confirm the worktree is still clean before the benchmark:

```bash
test -z "$(git status --porcelain)"
```

Then generate and verify P2.0d again:

```bash
uv run python -m scripts.run_release_runtime_benchmark \
  --policy-model-router-repo /Users/brunovicco/Projects/policy-model-router

uv run python -m scripts.verify_release_runtime_benchmark
```

A benchmark with a valid but failing SLO exits nonzero and is not release-acceptable.
Do not change the SLO policy to turn a failed result into a pass.

Commit only benchmark evidence:

```bash
git add artifacts/release/benchmark
git diff --cached --check
git commit -m "docs: refresh v0.2.0-rc2 runtime benchmark evidence"
test -z "$(git status --porcelain)"
```

## Stage 5 - capture frozen-source fresh-install evidence

This step does not test the current evidence commit. It archives and executes the
exact Governance source commit stored in the rc2 manifest.

Make sure no prior rc2 clean-install output exists. Do not delete evidence you need
to preserve. On the first rc2 run the directory should be absent.

```bash
uv run python -m scripts.capture_clean_install_release_evidence
```

Expected success output includes:

```text
[p2.0e.3-clean-install] GENERATED
```

The generated files are:

```text
artifacts/release/clean-install/clean-install-e2e.log
artifacts/release/clean-install/clean-install-evidence.json
```

Verify the receipt indirectly through the final verifier after the next stage, or
inspect it now:

```bash
python -m json.tool \
  artifacts/release/clean-install/clean-install-evidence.json >/dev/null
```

A failed clean-install run may leave the diagnostic log but will not create a
passing evidence receipt. Diagnose the failure before rerunning.

Commit the two clean-install artifacts:

```bash
git add artifacts/release/clean-install
git diff --cached --check
git commit -m "docs: record v0.2.0-rc2 clean-install evidence"
test -z "$(git status --porcelain)"
```

## Stage 6 - generate the single rc2 candidate root

The generator performs deep verification of P2.0a, P2.0b, P2.0c, P2.0d and the
P2.0e.1 clean-install receipt before writing the final index.

```bash
uv run python -m scripts.generate_release_candidate_evidence_index \
  --policy-model-router-repo /Users/brunovicco/Projects/policy-model-router \
  --credit-desk-repo /Users/brunovicco/Projects/multi-agent-credit-desk \
  --a2a-otel-kit-repo /Users/brunovicco/Projects/a2a-otel-kit
```

Generated files:

```text
artifacts/release/release-candidate-evidence-index.json
artifacts/release/release-candidate-subjects.sha256
```

Commit them:

```bash
git add \
  artifacts/release/release-candidate-evidence-index.json \
  artifacts/release/release-candidate-subjects.sha256

git diff --cached --check
git commit -m "docs: seal v0.2.0-rc2 release candidate evidence"
```

Now run the final offline verifier against the committed candidate:

```bash
uv run python -m scripts.verify_release_candidate_evidence_index \
  --policy-model-router-repo /Users/brunovicco/Projects/policy-model-router \
  --credit-desk-repo /Users/brunovicco/Projects/multi-agent-credit-desk \
  --a2a-otel-kit-repo /Users/brunovicco/Projects/a2a-otel-kit
```

It must report:

```text
[p2.0e.3] VERIFIED
[p2.0e.3] release: 0.2.0-rc2
```

The verifier also proves that no production runtime path changed between the
Governance source commit frozen in the manifest and the current evidence commit.

## Stage 7 - GitHub Artifact Attestation

Only after all rc2 evidence commits are pushed should the workflow
`.github/workflows/release-provenance.yml` be dispatched with:

```text
release_version = 0.2.0-rc2
```

The workflow:

- checks out all four exact source commits from the manifest;
- verifies the committed P2.0c subjects;
- runs the coordinated P2.0e.3 offline verifier;
- attests the P2.0c checksum subjects;
- independently attests the final rc2 evidence-index subject;
- uploads both Sigstore bundles;
- verifies both attestation sets with GitHub CLI.

A workflow failure blocks P2.0e.4.

## Final local gate before P2.0e.4

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy \
  apps/api/src \
  packages/governance-schemas/src \
  packages/policy-engine/src
uv run python scripts/quality_gate.py

git diff --check
test -z "$(git status --porcelain)"
```

Do not create `v0.2.0` in P2.0e.3. The final tag/release decision belongs to
P2.0e.4 after the rc2 evidence and attestations are confirmed.

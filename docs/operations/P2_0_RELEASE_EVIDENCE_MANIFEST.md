# P2.0a reproducible release evidence manifest

P2.0a creates a deterministic release evidence root across the four repositories participating in
the governed runtime scenario.

## Repositories

Recommended sibling checkout layout:

```text
/Users/brunovicco/Projects/
├── verifiable-ai-governance/
├── policy-model-router/
├── multi-agent-credit-desk/
└── a2a-otel-kit/
```

The commands accept other paths. Repository identity is validated from `remote.origin.url`.

## Why generation happens after the implementation commit

Do not generate and commit the manifest in the same implementation commit. The manifest should pin
the exact implementation commit that contains its generator, validator, schema, tests, ADR, and
runbook.

Use two commits:

```text
1. P2.0a implementation
2. release-manifest evidence
```

Verification intentionally reads the declared Git commit objects, so the second commit does not
invalidate the manifest.

## 1. Prepare clean repositories

```bash
cd /Users/brunovicco/Projects/verifiable-ai-governance
git status --short

cd /Users/brunovicco/Projects/policy-model-router
git status --short

cd /Users/brunovicco/Projects/multi-agent-credit-desk
git status --short

cd /Users/brunovicco/Projects/a2a-otel-kit
git status --short
```

Generation fails closed if any input repository is dirty or has untracked files.

## 2. Generate `v0.2.0-rc1` evidence

From the Governance repository:

```bash
cd /Users/brunovicco/Projects/verifiable-ai-governance

uv run python -m scripts.generate_release_evidence_manifest \
  --release-version 0.2.0-rc1 \
  --policy-model-router-repo ../policy-model-router \
  --credit-desk-repo ../multi-agent-credit-desk \
  --a2a-otel-kit-repo ../a2a-otel-kit \
  --output artifacts/release/release-manifest.json
```

Expected output:

```text
[p2.0a] GENERATED
[p2.0a] manifest: artifacts/release/release-manifest.json
[p2.0a] digest: <sha256>
```

The output is deterministic for the same selected Git commits and release version. It does not
contain a wall-clock generation timestamp.

## 3. Verify the manifest

```bash
uv run python -m scripts.verify_release_evidence_manifest \
  --manifest artifacts/release/release-manifest.json \
  --policy-model-router-repo ../policy-model-router \
  --credit-desk-repo ../multi-agent-credit-desk \
  --a2a-otel-kit-repo ../a2a-otel-kit
```

Expected:

```text
[p2.0a] VERIFIED
[p2.0a] manifest: artifacts/release/release-manifest.json
[p2.0a] digest: <same-sha256>
[p2.0a] Git, lockfiles, migrations, provenance, evidence and compatibility bindings verified
```

## 4. Inspect important claims

```bash
python - <<'PY'
import json
from pathlib import Path

path = Path("artifacts/release/release-manifest.json")
data = json.loads(path.read_text(encoding="utf-8"))

print("release:", data["release"]["version"])
print("manifest:", data["manifest_digest"])
print("migration:", data["database"]["alembic_head"])

for name, component in data["components"].items():
    print(name, component["project_version"], component["commit"])

for name, evidence in data["evidence"].items():
    print("evidence", name, evidence["sha256"])

print("compatibility:")
print(json.dumps(data["compatibility"], indent=2, sort_keys=True))
PY
```

## 5. Commit the evidence separately

```bash
git add artifacts/release/release-manifest.json
git commit -m "docs: record v0.2.0-rc1 release evidence manifest"
```

Then verify again. The current Governance `HEAD` is now newer than the manifest's selected
Governance commit, but verification still succeeds because it reads the exact declared Git object.

```bash
uv run python -m scripts.verify_release_evidence_manifest \
  --manifest artifacts/release/release-manifest.json \
  --policy-model-router-repo ../policy-model-router \
  --credit-desk-repo ../multi-agent-credit-desk \
  --a2a-otel-kit-repo ../a2a-otel-kit
```


## Squash-merge compatibility

P1.9e records the implementation commit used to generate its live evidence. The GitHub PR may later
be integrated by squash, so that implementation commit is not necessarily an ancestor of `main`.
P2.0a handles this without weakening verification:

```text
exact commit      -> relation = exact
normal merge      -> relation = descendant
squash/rebase     -> relation = squash_equivalent
```

`squash_equivalent` is accepted only when every path changed by the original single-parent evidence
commit has identical bytes at the selected release commit. The manifest records the count and a
canonical SHA-256 over that attested path snapshot. Any drift on one of those paths fails closed.

The original evidence commit object must still be available in the local Git object database so the
comparison can be re-derived.

## Evidence limitation surfaced by P2.0a

The committed P1.9 live report records the Governance and Credit Desk commits and the installed
`a2a-otel-kit` runtime version. It proves Router behavior through `decision_source=policy_model_router`
but does not record the Policy Model Router Git SHA.

P2.0a pins the selected Router SHA while explicitly retaining this limitation. Do not rewrite it as
an exact P1.9 Router attestation. A future E2E report can add that source commit to close the gap.

## No secret material

The manifest contains only source metadata, bounded compatibility information, file sizes, and
SHA-256 digests. It never reads runtime key files or environment secrets.

## Next stages

P2.0b should attach content-addressed SBOM and vulnerability reports to this release evidence root.
P2.0c should add build/image provenance and attestations.

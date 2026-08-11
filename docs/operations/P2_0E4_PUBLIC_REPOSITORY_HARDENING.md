# P2.0e.4 - Public repository hardening

## Purpose

P2.0e.4 prepares the exact public source tree that will later be frozen for `0.2.0-rc2`. It changes
repository hygiene, documentation and reference-demo CI. It does **not** generate rc2 evidence,
change runtime behavior, create a tag or publish a release.

The release sequence after this phase is:

```text
P2.0e.3  coordinated rc2 evidence tooling
  → P2.0e.4  public repository hardening
  → source freeze
  → P2.0e.5  generate and attest 0.2.0-rc2 evidence
  → P2.0e.6  final validation / v0.2.0 tag and release
```

## Scope

This phase:

- removes the tracked root `CLAUDE.md` after migrating durable guidance;
- adds tool-neutral `docs/DEVELOPMENT.md`;
- adds a Git-tracked-path repository-hygiene gate;
- updates `.gitignore` and `.dockerignore` for local coding-tool state;
- integrates hygiene into the repository quality gate;
- updates EN/PT-BR public positioning and current capability status;
- adds EN/PT-BR five-minute walkthroughs;
- updates the canonical demo guide and scenario boundary;
- adds dedicated `Reference Demo` CI;
- amends P2.0e.3 release documentation so source freeze occurs after this phase.

It deliberately does not add multi-platform container publication or fabricate new visual assets.

## Apply

Start from the branch containing committed P2.0e.1, P2.0e.2 and P2.0e.3 tooling.

```bash
cd /Users/brunovicco/Projects/verifiable-ai-governance

git status --short
git switch -c docs/p2.0e4-public-repository-hardening

unzip -o \
  /Users/brunovicco/Downloads/verifiable-ai-governance-p2.0e4-complete.zip \
  -d /Users/brunovicco/Projects/verifiable-ai-governance

git rm CLAUDE.md
```

`git rm CLAUDE.md` is intentional. ZIP archives do not encode a source-tree deletion reliably for
this patch workflow, so the deletion is an explicit bounded step.

## Validate hygiene first

```bash
uv run python scripts/validate_repository_hygiene.py
uv run pytest apps/api/tests/test_repository_hygiene.py
```

Expected:

```text
[repository-hygiene] PASS
```

The validator uses `git ls-files`; ignored local `.claude/`, `.codex/` or similar directories do
not fail the gate unless they become tracked.

## Validate canonical public proof

The dedicated GitHub workflow runs against PostgreSQL. Locally, use the existing canonical seed
regression suite plus migration history:

```bash
uv run pytest \
  apps/api/tests/test_canonical_demo_seed.py \
  apps/api/tests/test_migration_history.py \
  apps/api/tests/test_repository_hygiene.py
```

If a dedicated empty PostgreSQL demo database is available, the workflow-equivalent sequence is:

```bash
export APP_ENV=test
export DATABASE_URL='postgresql+asyncpg://governance:governance@127.0.0.1:5432/governance_reference_demo'
export AUTO_CREATE_SCHEMA=false

uv run alembic -c apps/api/alembic.ini upgrade head
uv run python -m scripts.seed_canonical_demo --output /tmp/canonical-demo-created.json
uv run python -m scripts.seed_canonical_demo \
  --check \
  --output /tmp/canonical-demo-checked.json
```

Do not point this sequence at a production or shared data set.

## Validate documentation boundaries

Check that no public document still describes runtime telemetry as merely planned or claims the
canonical seed performs a live Router network integration:

```bash
rg -n "Runtime telemetry ingestion.*Planned|Ingestão de telemetria de runtime.*Planejada" \
  README.md README.pt-BR.md docs/product docs/demo || true

rg -n "Claude Code|\.claude/|AGENTS\.md|CLAUDE\.md" \
  README.md README.pt-BR.md CONTRIBUTING.md docs/DEVELOPMENT.md docs/demo \
  docs/product || true
```

The second command may show the hygiene policy itself where those filenames are intentionally
explained. It must not show them as required development tools.

## Prohibited Python import check

P2.0e.4 must not introduce postponed-annotation imports:

```bash
rg -n '^from __future__ import annotations$' \
  scripts/validate_repository_hygiene.py \
  apps/api/tests/test_repository_hygiene.py
```

Expected: no output.

## Full gate

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy \
  apps/api/src \
  packages/governance-schemas/src \
  packages/policy-engine/src
uv run python scripts/quality_gate.py
git diff --check
```

The Vite `configLoader: native` warning may still appear during tests. It is non-blocking and is not
part of this phase unless it becomes a failing build condition.

## Review staged scope

Stage only P2.0e.4 files, including the deletion:

```bash
git add \
  .dockerignore \
  .gitignore \
  .github/workflows/reference-demo.yml \
  CONTRIBUTING.md \
  README.md \
  README.pt-BR.md \
  apps/api/tests/test_repository_hygiene.py \
  docs/DEVELOPMENT.md \
  docs/README.md \
  docs/adr/0052-rc2-release-evidence-refresh.md \
  docs/adr/0053-public-repository-hardening.md \
  docs/demo/CANONICAL_DEMO_SCENARIO.md \
  docs/demo/DEMO_GUIDE.md \
  docs/demo/FIVE_MINUTE_WALKTHROUGH.md \
  docs/demo/FIVE_MINUTE_WALKTHROUGH.pt-BR.md \
  docs/executive/EXECUTIVE_OVERVIEW.md \
  docs/operations/OBSERVABILITY.md \
  docs/operations/P2_0E3_RC2_RELEASE_EVIDENCE_REFRESH.md \
  docs/operations/P2_0E4_PUBLIC_REPOSITORY_HARDENING.md \
  docs/product/CAPABILITY_MATRIX.md \
  docs/product/ROADMAP.md \
  scripts/quality_gate.py \
  scripts/validate_repository_hygiene.py \
  CLAUDE.md

git diff --cached --check
git diff --cached --name-status
```

The staged list must show `CLAUDE.md` as deleted, not recreated.

Commit suggestion:

```bash
git commit -m "docs: harden public repository before v0.2.0 freeze"
```

## Source-freeze handoff

After the commit, validate a clean worktree:

```bash
git status --short
uv run python scripts/validate_repository_hygiene.py
uv run python scripts/quality_gate.py
```

Only after the public tree is accepted should the source SHA be frozen for P2.0e.5.

Do **not** generate the rc2 manifest, security evidence, provenance, runtime benchmark,
clean-install evidence or candidate index as part of P2.0e.4. Those operations belong to P2.0e.5.

Any later source, workflow or documentation change intended for v0.2.0 changes the candidate tree
and must occur before P2.0e.5 source freeze, or the rc2 evidence chain must be restarted.

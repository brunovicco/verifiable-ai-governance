# ADR 0053 - Harden the public repository before the v0.2.0 source freeze

- **Status:** Accepted
- **Date:** 2026-08-11
- **Decision owners:** Engineering and architecture

## Context

The v0.2.0 release candidate now contains substantial governance, runtime-assurance and
release-evidence behavior. The public repository is therefore part of the assurance surface: a
reviewer needs to distinguish durable engineering contracts from local coding-tool state, and the
README/capability documents must describe the implementation that will actually be frozen by the
release manifest.

The repository still had a root `CLAUDE.md` with valuable but tool-specific development guidance.
The public ignore policy did not prevent similar agent/tool state from being committed later. The
README and product documents also lagged implemented runtime telemetry, assurance, governed
actuation and release-evidence capabilities.

Generating the final rc2 evidence before correcting those issues would freeze a source commit that
was technically valid but not the public tree intended for v0.2.0.

## Decision

Perform a dedicated public-repository hardening phase before the rc2 source freeze.

### Tool-neutral public engineering contract

Durable development guidance belongs in:

- `CONTRIBUTING.md`;
- `docs/DEVELOPMENT.md`;
- architecture, security and governance documentation;
- ADRs and operational runbooks;
- repository-owned validation scripts.

Tool-specific assistant/editor state is local-only. The root `CLAUDE.md` is removed after its
durable guidance is represented in tool-neutral documentation.

### Regression-protected hygiene

`scripts/validate_repository_hygiene.py` evaluates **tracked Git paths**, not arbitrary files in a
developer's working directory. This distinction allows local tools to exist while preventing their
state from becoming part of the public source tree.

The gate rejects tracked coding-agent directories/files, local environment files, caches and other
generated state. `.gitignore` and `.dockerignore` contain the corresponding policy. The validator
is included in `scripts/quality_gate.py` and has regression tests.

### Public proof structure

The English and Brazilian Portuguese READMEs are organized around the claim the repository proves:

```text
Policy
  → Approval
  → Signed Authorization
  → Runtime Enforcement
  → Violation / Runtime Assurance
  → Governed Response
  → Evidence
```

The capability matrix and roadmap are reviewed against implemented behavior. Runtime telemetry and
governed actuation are no longer described as merely planned, while broader long-horizon drift and
enterprise control-effectiveness analytics remain explicitly partial.

### Deterministic reference-demo CI

A dedicated `Reference Demo` workflow validates the public canonical story against an empty
PostgreSQL database. It applies migrations, seeds and checks the deterministic scenario, and runs
identity/migration/hygiene regressions.

The workflow intentionally does not claim to be the live Policy Model Router integration test. The
canonical seed uses a deterministic local Router adapter; the cross-repository governed-actuation
E2E remains the live integration proof.

### Visual evidence

Reuse the existing real synthetic-data demo capture. Do not add fabricated or purely decorative
screenshots to satisfy a presentation checklist. New images should be added only when produced by a
fresh reproducible demo capture and when they add evidence not already represented.

### Release sequencing

P2.0e.3 delivered the coordinated rc2 evidence tooling. P2.0e.4 completes the public source tree.
Only then may the source commit be frozen and P2.0e.5 materialize the rc2 evidence. P2.0e.6 owns the
final validation, tag and release.

## Consequences

### Positive

- public source no longer advertises one maintainer's coding assistant as an engineering
  dependency;
- durable contributor guidance remains available in neutral documentation;
- accidental reintroduction of local tooling/state becomes a failing quality check;
- README, capability matrix and roadmap reflect the implemented runtime-governance story;
- reviewers get a short, executable path through the canonical scenario;
- release evidence will bind the polished public source instead of an earlier technical snapshot.

### Costs

- maintainers who use local coding tools must keep their configuration ignored;
- documentation updates become release-relevant source changes before source freeze;
- the dedicated reference-demo workflow adds a small CI cost;
- the final rc2 evidence must be generated after this phase rather than immediately after the
  P2.0e.3 tooling commit.

## Rejected alternatives

### Keep tool-specific instructions public because they help maintainers

Rejected. Durable rules are useful; coupling those rules to one assistant/tool is not necessary.
The rules are moved to neutral documentation and local configuration remains possible.

### Ban all files containing the word “agent”

Rejected. Agents are first-class product concepts. Hygiene is path/state based, not keyword based.

### Validate every untracked local file

Rejected. The public-repository contract concerns tracked source. Developers may use local ignored
tools without making the quality gate fail.

### Generate rc2 evidence first and polish documentation afterwards

Rejected. README, workflows and documentation are part of the source commit. Post-freeze polishing
would make the published tree differ from the source represented by release evidence.

### Add new screenshots without rerunning a real demo

Rejected. Presentation must not create evidence-looking artifacts that were not captured from an
executable state.

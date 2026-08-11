# Contributing

Thank you for considering a contribution to Verifiable AI Governance.

## Principles

Changes should preserve:

- deterministic and explainable governance decisions;
- explicit authorization and segregation of duties;
- immutable historical review evidence;
- fail-closed behavior for critical dependencies;
- data minimization;
- stable, versioned contracts;
- honest separation of implemented, partial and planned capabilities.

## Before opening a pull request

1. Open or reference an issue for material behavior changes.
2. Identify affected users, contracts and threat boundaries.
3. Add or update an ADR for a material architectural decision.
4. Include positive and negative tests.
5. Update relevant documentation and capability status.
6. Avoid secrets, personal data, prompts, evidence content and production identifiers.
7. Keep local editor/coding-agent state outside the tracked public repository.

The tool-agnostic setup, architecture and testing conventions live in
[`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## Development setup

```bash
make setup
docker compose up -d postgres
make migrate
make dev-api
```

In another terminal:

```bash
make dev-web
```

Or run the complete local stack:

```bash
cp .env.example .env
docker compose up --build
```

## Quality gate

Before submitting:

```bash
make quality
```

The repository-owned gate includes locked dependencies, public-repository hygiene, Python
lint/type checks/tests, portal tests/lint and a production build. Fresh-install migration coverage
also runs in CI.

## Definition of done

A feature is not complete with only a screen or endpoint. Where applicable, it requires:

- domain or application contract;
- authorization and segregation-of-duties behavior;
- persistence and versioning;
- transaction and concurrency semantics;
- audit event;
- safe dependency-failure behavior;
- positive and negative tests;
- migration and rollback/forward-fix consideration;
- user-facing and technical documentation;
- capability-matrix update.

## Repository hygiene

Engineering rules that are durable for contributors belong in public documentation, ADRs and
repository-owned validation scripts. Tool-specific local state such as `.agents/`, `.claude/`,
`.codex/`, harness configuration and assistant instruction files is intentionally ignored.

Run the focused gate with:

```bash
uv run python scripts/validate_repository_hygiene.py
```

Do not weaken this policy to make local tooling easier to commit.

## Pull request description

Include:

```text
Problem and user outcome
Behavior and architectural decision
Security/privacy impact
Files and contracts affected
Tests and evidence
Migration or operational impact
Documentation updated
Explicitly out of scope
```

## Commit style

Use clear, intentional commits. Conventional Commit prefixes are recommended, for example:

```text
feat: add governed evidence export
fix: reject stale asset review during routing
refactor: isolate directory authorization adapter
docs: add runtime threat model
```

## Security issues

Do not open a public issue for a suspected vulnerability. Follow `SECURITY.md`.

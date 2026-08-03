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

1. open or reference an issue for material behavior changes;
2. identify affected users, contracts and threat boundaries;
3. add or update an ADR for a material architectural decision;
4. include positive and negative tests;
5. update relevant documentation and capability status;
6. avoid secrets, personal data, prompts, evidence content and production identifiers.

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

The quality gate should remain reproducible and include locked dependencies, Python
lint/type checks/tests, portal tests/lint and production build.

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

Use clear, intentional commits. Conventional Commit prefixes are recommended, for
example:

```text
feat: add governed evidence export
fix: reject stale asset review during routing
refactor: isolate directory authorization adapter
 docs: add runtime threat model
```

## Security issues

Do not open a public issue for a suspected vulnerability. Follow `SECURITY.md`.

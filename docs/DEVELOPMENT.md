# Development guide

- **Status:** Current
- **Owner:** Engineering
- **Last reviewed:** 2026-08-11
- **Review trigger:** Toolchain, architecture or quality-gate change

This document is the tool-agnostic engineering entry point for the repository. Local editor,
coding-agent and assistant configuration is intentionally not part of the public source tree.

## Repository layout

```text
apps/web                     Next.js portal
apps/api                     FastAPI API, application services and adapters
packages/governance-schemas  Shared governance contracts and taxonomies
packages/policy-engine       Deterministic risk/control policy engine
packages/document-templates  Versioned business-document templates
docs                         Product, governance, architecture and operations
scripts                      Repository-owned validation and operational tooling
```

Python is managed as a `uv` workspace. The web application is an npm workspace under
`apps/web`.

## Setup

For the complete local stack:

```bash
cp .env.example .env
docker compose up --build
```

For application development without containerizing the API/web processes:

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

## Canonical reference demo

Populate the deterministic reference scenario:

```bash
make seed-demo
```

Validate an existing scenario without creating or repairing it:

```bash
uv run python -m scripts.seed_canonical_demo --check
```

The scenario drives real Governance application use cases. Its seed-time model-router adapter is
deterministic and local; it must not be confused with the separate cross-repository live Router
and governed-actuation E2E. See [Canonical demo](demo/CANONICAL_DEMO_SCENARIO.md) and the
[Five-minute walkthrough](demo/FIVE_MINUTE_WALKTHROUGH.md).

## Quality gate

Run the complete repository-owned gate before proposing a change:

```bash
uv run python scripts/quality_gate.py
```

Available checks can be listed or run independently:

```bash
uv run python scripts/quality_gate.py --list
uv run python scripts/quality_gate.py --check hygiene
uv run python scripts/quality_gate.py --check pytest
```

The gate covers locked dependencies, repository hygiene, Ruff, strict typing, Python tests, web
tests, web lint and a production web build. CI also validates fresh-install migrations from an
empty PostgreSQL database.

## Architecture rules

The API follows explicit dependency direction:

```text
routers / entrypoints
        ↓
application use cases and ports
        ↓
domain rules

adapters → application/domain ports
```

Domain and application code must not acquire infrastructure dependencies merely for convenience.
Framework-specific input validation and error translation belong at the edges. Material changes to
dependency direction, trust boundaries, authorization, evidence semantics or durable contracts
require an ADR.

Start with:

- [Architecture](architecture/ARCHITECTURE.md)
- [Trust boundaries](architecture/TRUST_BOUNDARIES.md)
- [Security model](security/SECURITY_MODEL.md)
- [Evidence model](governance/EVIDENCE_MODEL.md)

## Database migrations

Schema changes use Alembic and must remain valid from an empty database as well as from an existing
supported database:

```bash
make migrate
make fresh-install-migrations
```

Do not replace migration history with ORM `create_all` behavior. The migration chain is an
operational contract and has dedicated regression coverage.

## Tests

Useful focused commands:

```bash
uv run pytest apps/api/tests/test_inventory.py
uv run pytest apps/api/tests/test_canonical_demo_seed.py
uv run pytest packages/policy-engine/tests
npm run test:web
```

Unit tests should remain deterministic and avoid real external network calls. Use dedicated
integration or E2E paths when the behavior being proved is specifically about infrastructure or
cross-service boundaries.

## Repository hygiene

Public source must remain independent of a maintainer's local coding tools. The repository gate
rejects tracked local state such as `.agents/`, `.claude/`, `.codex/`, `.harness.json`,
`AGENTS.md`, `CLAUDE.md`, caches and non-example `.env*` files.

Durable engineering guidance belongs in `CONTRIBUTING.md`, this guide, architecture/security docs,
runbooks and ADRs. Tool-specific local configuration may exist on a developer machine, but it must
remain ignored and outside container build contexts.

Validate explicitly with:

```bash
uv run python scripts/validate_repository_hygiene.py
```

## Security and privacy

Do not commit secrets, production identifiers, prompts, model responses, customer data or raw
evidence content. New integrations must define authentication, authorization, timeouts, bounded
failure behavior, data minimization and audit semantics before being treated as production-ready.

Security issues must follow [SECURITY.md](../SECURITY.md), not a public issue.

## Pull requests

Read [CONTRIBUTING.md](../CONTRIBUTING.md). Keep changes focused, update documentation when public
behavior changes and include the commands/evidence used to validate the change.

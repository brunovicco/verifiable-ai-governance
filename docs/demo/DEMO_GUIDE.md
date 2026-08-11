# Demo guide

- **Status:** Current
- **Owner:** Product and engineering
- **Last reviewed:** 2026-08-11
- **Review trigger:** Demo topology, seed contract or public-deployment change

This guide explains how to execute the reference demo and how to interpret its evidence. For a
reviewer who wants only the shortest evaluation path, use the
[Five-minute walkthrough](FIVE_MINUTE_WALKTHROUGH.md).

## Demo modes

The project has three deliberately separate proof modes.

### 1. Public read-only demo

The public environment is a browsing surface for synthetic governance data. Its deployed version
may lag the repository release candidate. The root README states the currently deployed version
explicitly.

Write operations, evidence uploads and governance decisions are blocked at the reverse proxy. The
public demo should not be used to infer that every newer release-candidate runtime capability is
already deployed there.

### 2. Local canonical demo

The canonical local scenario is deterministic and intended for reproducible review. It drives real
Governance application use cases and produces stable semantic identities for the reference credit
scenario.

The seed uses a deterministic local Policy Model Router adapter. This is intentional: the fixture
proves Governance behavior without making a network dependency part of deterministic seed setup.
It is not a substitute for the separate live cross-repository E2E.

### 3. Runtime/release proof

Live Router/telemetry/governed-actuation behavior and release provenance/security/SLO evidence have
separate E2E and release-evidence workflows. These are the appropriate sources when the question
is whether an external runtime boundary or frozen release was actually verified.

## Start the local stack

Prerequisite: Docker Desktop or another Docker Compose-compatible environment.

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Portal: `http://localhost:3000`
- API documentation: `http://localhost:8000/docs`

ClamAV can take additional time on first start while signatures are prepared. Evidence uploads
remain fail-closed until the scanner reports readiness.

## Seed the canonical story

```bash
make seed-demo
```

The equivalent direct command is:

```bash
uv run python -m scripts.seed_canonical_demo
```

By default it writes:

```text
artifacts/demo/canonical-seed-manifest.json
```

Validate the existing scenario without changing it:

```bash
uv run python -m scripts.seed_canonical_demo --check
```

Rerunning the normal seed is idempotent. Destructive reset is guarded by an explicit confirmation
and must only be used against a dedicated non-production demo database.

## What to inspect

Use the canonical initiative:

```text
[DEMO-CANONICAL] Análise de Crédito PJ Assistida e Auditável
```

Recommended sequence:

1. initiative context and deterministic risk;
2. applicable controls;
3. AI impact, RIPD and international-processing assessments;
4. approval gates and immutable review state;
5. AI system inventory;
6. approved model and agent review scope;
7. allowed runtime routing decision;
8. blocked out-of-scope routing decision;
9. correlated incident;
10. runtime/release runbooks for evidence beyond the deterministic fixture.

The stable top-level IDs are documented in
[`CANONICAL_DEMO_SCENARIO.md`](CANONICAL_DEMO_SCENARIO.md).

## Visual evidence

The root README includes `docs/assets/dashboard-demo.gif`, captured from a successful synthetic
portal walkthrough. P2.0e.4 intentionally reuses that existing evidence instead of manufacturing
new images without a fresh reproducible capture session.

A screenshot or GIF is presentation evidence, not release assurance. Claims about runtime
integration, security scans, SLOs or frozen-source reproducibility must be backed by their
repository-owned machine-verifiable evidence paths.

## Reference Demo CI

`.github/workflows/reference-demo.yml` proves that the public canonical story can be rebuilt from
an empty PostgreSQL database:

```text
locked install
  → repository hygiene
  → Alembic migrations
  → canonical seed
  → canonical --check
  → identity/migration/hygiene regression tests
```

This workflow deliberately does not require sibling repositories or GitHub attestation
permissions.

## Live runtime evidence

For the cross-repository governed runtime path, use:

- [`../operations/P1_9_GOVERNED_ACTUATION_E2E.md`](../operations/P1_9_GOVERNED_ACTUATION_E2E.md)
- runtime benchmark/SLO evidence under `artifacts/release/` after the corresponding release phase
- P2.0 operations runbooks for security, provenance and release-candidate evidence

## Production boundary

Do not carry demo defaults into production without explicit review. Production deployments must
supply organization-owned identity configuration, authorization mappings, secrets/key management,
private storage controls, network policy, retention, alerting, recovery objectives, runtime
thresholds and integration ownership.

Synthetic data, local identities, example policy values and deterministic seed adapters are demo
properties, not recommended production defaults.

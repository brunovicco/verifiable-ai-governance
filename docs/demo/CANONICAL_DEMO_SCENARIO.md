# Canonical demo scenario - governed corporate credit

- **Status:** Current
- **Owner:** Product and architecture
- **Last reviewed:** 2026-08-11
- **Review trigger:** Canonical seed contract, runtime-governance flow or public demo change

## Purpose

The canonical scenario provides one reproducible story that can be used to evaluate the platform
without inventing production data or relying on mutable manual setup.

It represents a corporate-credit workflow in which deterministic rules calculate the business
result and an AI agent may prepare a narrative opinion for human review. The model/agent path is
governed, scoped and observable; the agent is not the final credit authority.

The scenario is synthetic. It is an example of how a regulated workflow can use the platform, not a
financial-services policy overlay or a production credit implementation.

## Governance story

```text
Proposal
  → deterministic preliminary risk
  → required controls and structured assessments
  → multidisciplinary approval
  → AI system inventory
  → model review
  → agent review
  → scope-bound runtime authorization
  → allowed routing decision
  → blocked out-of-scope routing decision
  → incident / runtime evidence
```

The wider repository then extends the runtime story through sanitized telemetry, runtime assurance,
governed actuation and release evidence. Those cross-service paths have their own E2E/runbooks and
must not be confused with the seed fixture itself.

## Stable scenario identity

The seed uses semantic UUIDv5 identities so a fresh database produces the same top-level reference
objects instead of random UUIDs.

| Object | Stable ID |
|---|---|
| Scenario | `credit-pj-governed-runtime` |
| Initiative | `e3095057-9408-561b-a755-cfc9f1453af5` |
| AI system | `eabfd874-b6ca-5319-b7e1-30cae5d798df` |
| Approved model | `9a798288-ea72-5e4d-ac33-dfc7533d80cb` |
| Out-of-scope model | `150df55c-7ca6-551b-826d-545ccbe1dff5` |
| Agent | `565aa2b9-ead9-59e6-89a9-18920cced7ce` |
| Allowed routing decision | `1c384bfc-4126-5fda-8d58-bd63fd73aac4` |
| Blocked routing decision | `32f86499-5b44-5580-870c-9c5a13bf9ff3` |
| Incident | `29629ff5-c689-5d4e-8b22-5812e2e07a65` |

Assessments, review submissions, approvals and evidence records derive stable IDs from semantic
keys as well. Stable identity is a demo/release-evidence property; normal production entities are
not globally assigned these demo IDs.

## What the seed actually proves

`python -m scripts.seed_canonical_demo` drives Governance application services to create and
validate the scenario. It proves that the Governance domain can persist and reconstruct the
approved and blocked reference states.

For reproducibility, the seed uses a **deterministic local Policy Model Router adapter**. It chooses
the expected logical group from the fixed task identity and returns a contract-compatible decision
that Governance then revalidates. Therefore:

- the seed proves Governance routing enforcement and evidence semantics deterministically;
- the seed does **not** prove a live network call to `policy-model-router`;
- the cross-repository governed-actuation E2E is the live integration proof for that boundary.

This distinction is intentional and regression-protected in public documentation.

## Scenario characteristics

The initiative is deliberately high-assurance:

- material decision impact;
- restricted data classification;
- personal and sensitive data flags;
- regulated context;
- international processing;
- AI agent usage;
- MCP usage;
- human final approval;
- explicit model and agent reviews;
- an approved logical routing group;
- an out-of-scope routing attempt that must be blocked.

The structured assessments include AI impact, RIPD/privacy and international-processing context.
The evidence set and approval gates use the normal application contracts instead of bypassing the
workflow with direct fixture inserts.

## Run locally

Start the stack and seed:

```bash
cp .env.example .env
docker compose up --build
make seed-demo
```

Or invoke the CLI directly:

```bash
uv run python -m scripts.seed_canonical_demo
```

Validate without mutation:

```bash
uv run python -m scripts.seed_canonical_demo --check
```

The command writes a deterministic JSON summary to
`artifacts/demo/canonical-seed-manifest.json` by default. The output path can be changed with
`--output`.

## Reset safeguards

Reset is intentionally destructive and is allowed only with an explicit confirmation on a
non-production environment. Use it only for a dedicated demo database. Routine reruns are
idempotent and do not require reset.

## CI proof

`.github/workflows/reference-demo.yml` runs the public reference-demo gate against an empty
PostgreSQL database:

1. install the locked workspace;
2. verify repository hygiene;
3. apply the full Alembic migration chain;
4. create the canonical scenario;
5. run `--check` against the resulting scenario;
6. execute deterministic identity, migration-history and hygiene regression tests.

This workflow is intentionally narrower than release evidence. Security scanners, live sibling
repositories, runtime benchmark/SLO and attestations remain part of their dedicated evidence paths.

## Related proof

- [Five-minute walkthrough](FIVE_MINUTE_WALKTHROUGH.md)
- [Demo guide](DEMO_GUIDE.md)
- [Governed actuation E2E](../operations/P1_9_GOVERNED_ACTUATION_E2E.md)
- [Capability matrix](../product/CAPABILITY_MATRIX.md)
- P2.0 release-evidence runbooks under `docs/operations/`

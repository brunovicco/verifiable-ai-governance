# Five-minute walkthrough

- **Status:** Current
- **Owner:** Product and architecture
- **Last reviewed:** 2026-08-11
- **Review trigger:** Canonical demo, portal navigation or runtime evidence change

This is the shortest path for evaluating what Verifiable AI Governance proves. It uses only
synthetic data and separates UI evidence, deterministic fixture evidence and live integration
proofs.

## Minute 0-1 - understand the claim

Read the first section of the root `README.md` and keep this chain in mind:

```text
Policy
  → Approval
  → Signed Authorization
  → Runtime Enforcement
  → Violation / Runtime Assurance
  → Governed Response
  → Evidence
```

The important design choice is that runtime authorization is derived from reviewed scope. A model
or agent is not trusted merely because an application can technically call it.

## Minute 1-2 - inspect the governance state

In the portal, open the canonical initiative:

**`[DEMO-CANONICAL] Análise de Crédito PJ Assistida e Auditável`**

Look for:

- deterministic risk and applicable controls;
- submitted structured assessments;
- independent approval gates;
- the resulting AI system;
- reviewed model and agent assets.

The existing dashboard GIF in the root README is a real capture of this style of demo state, not a
mock marketing illustration.

## Minute 2-3 - follow the runtime boundary

The canonical scenario contains two routing outcomes:

- allowed decision: `1c384bfc-4126-5fda-8d58-bd63fd73aac4`;
- blocked decision: `32f86499-5b44-5580-870c-9c5a13bf9ff3`.

The approved model uses ID `9a798288-ea72-5e4d-ac33-dfc7533d80cb`; the intentionally
out-of-scope model uses `150df55c-7ca6-551b-826d-545ccbe1dff5`.

The point is not merely that a router can return “deny”. Governance revalidates the result against
the approved scope and preserves trusted fail-closed denial information as runtime evidence.

## Minute 3-4 - inspect incident and assurance boundaries

The blocked reference path correlates to incident:

`29629ff5-c689-5d4e-8b22-5812e2e07a65`

Use the system/incident views and API documentation to inspect the recorded relationship among the
governed asset, runtime decision and incident.

For the wider runtime path, read
[`P1_9_GOVERNED_ACTUATION_E2E.md`](../operations/P1_9_GOVERNED_ACTUATION_E2E.md). That proof covers
the live cross-repository boundary for Router/runtime telemetry/governed actuation. The canonical
seed itself intentionally uses a deterministic local Router adapter.

## Minute 4-5 - verify reproducibility instead of trusting the UI

Run:

```bash
uv run python -m scripts.seed_canonical_demo --check
uv run python scripts/validate_repository_hygiene.py
```

Then inspect the repository's P2.0 release-evidence runbooks. The release chain binds frozen source
to security, provenance, runtime benchmark/SLO, clean-install evidence and a final candidate root.

Before v0.2.0, the final `0.2.0-rc2` evidence is regenerated only after the public source tree is
frozen. This means documentation/workflow changes are included in the source that the evidence
claims to represent.

## If you have another five minutes

Recommended order:

1. [Capability matrix](../product/CAPABILITY_MATRIX.md)
2. [Architecture](../architecture/ARCHITECTURE.md)
3. [Threat model](../security/THREAT_MODEL.md)
4. [Evidence model](../governance/EVIDENCE_MODEL.md)
5. [Development guide](../DEVELOPMENT.md)

## Local execution

For a full local portal/API run:

```bash
cp .env.example .env
docker compose up --build
make seed-demo
```

Open `http://localhost:3000`. The first ClamAV startup can take longer while signatures are
prepared; evidence upload remains fail-closed until scanning is ready.

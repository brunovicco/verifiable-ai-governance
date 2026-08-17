# PH-1 Governance Intelligence compatibility gate

- **Status:** Current
- **Owner:** Platform engineering and architecture
- **Last reviewed:** 2026-08-16
- **Review trigger:** Contract, packaging, Python boundary or consumer-repository change
- **Authoritative sources:** ADR 0055, verifier scripts and compatibility workflow

PH-1 verifies that Governance Finding v1 can be consumed from the built `governance-schemas` wheel
without importing the Governance source tree. It is a package/contract gate, not a live service E2E.

## Local verification

Run against the current local consumer checkouts:

```bash
uv run python scripts/verify_governance_intelligence_compatibility.py \
  --consumer-repo policy-model-router=../policy-model-router \
  --consumer-repo multi-agent-credit-desk=../multi-agent-credit-desk
```

The consumer values use `NAME=PATH`, may be repeated and must point to directories containing a
`pyproject.toml`. The verifier reads Git revisions but does not change either checkout.

To run only the repository-owned artifact check with an empty external adapter:

```bash
uv run python scripts/quality_gate.py \
  --check governance-intelligence-compatibility
```

Expected terminal markers include:

```text
[ph-1] wheel=governance_schemas-... package=governance-schemas ...
[ph-1] consumer=policy-model-router revision=... PASS
[ph-1] consumer=multi-agent-credit-desk revision=... PASS
[ph-1] PASSED consumers=2
```

## What the gate proves

1. `uv build` produces exactly one `governance-schemas` wheel.
2. The wheel contains the public package and Governance Intelligence module.
3. Package metadata retains the intended Python and Pydantic-only dependency boundary.
4. Shipped Python sources do not import the application, model providers or agent frameworks.
5. The wheel is installed into an ephemeral target without dependency resolution.
6. Python `-I` imports `governance_schemas` from that target while running from each consumer root.
7. The checked-in v1 fixture validates through public exports.
8. Authority escalation, trusted status, non-advisory status and invalid confidence are rejected.

Pydantic is supplied by the locked Governance environment. No consumer dependency or service is
started, and no consumer module is imported. Existing runtime cross-repository E2E tests remain the
evidence for service-level interoperability.

## CI behavior

`.github/workflows/governance-intelligence-compatibility.yml` checks out the current default branch
of Policy Model Router and Credit Desk. It runs:

- on pull requests and `main` pushes that change the contract, package, verifier or lock file;
- weekly, so consumer drift is detected even when Governance has not changed;
- manually through `workflow_dispatch`.

The normal repository quality gate also runs the artifact proof with an ephemeral empty consumer.

## Failure triage

| Failure | Check |
|---|---|
| wheel build or count | package build configuration and Hatchling inputs |
| missing module/export | wheel contents and `governance_schemas.__init__` |
| dependency/import coupling | package metadata and shipped imports; review ADR 0054/0055 |
| wrong import origin | isolated command and ephemeral target installation |
| fixture validation | contract implementation versus checked-in v1 fixture |
| negative mutation accepted | closed Pydantic models and advisory literals |
| consumer path invalid | checkout path and `pyproject.toml` presence |

Do not weaken a negative assertion to make an incompatible change pass. If the intended change
alters v1 compatibility or package boundaries, stop and make the PH-2 evolution decision first.

Temporary build/install directories are removed automatically. A failed run does not require
consumer cleanup.

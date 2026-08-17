# PH-2 Governance Intelligence contract evolution

- **Status:** Current
- **Owner:** Platform engineering and architecture
- **Last reviewed:** 2026-08-17
- **Review trigger:** Governance Finding model, schema, lifecycle or package-boundary change
- **Authoritative sources:** ADR 0056, compatibility policy, schema snapshots and PH-2 verifier

PH-2 freezes every supported Governance Finding wire version and provides a fail-closed process for
adding, deprecating or removing versions. It does not introduce a new version by itself: `1.0`
remains the only current and supported schema.

## Current compatibility set

| Wire version | Status | Introduced in package | Reads |
|---|---|---|---|
| `1.0` | current | `0.1.0` | `1.0` |

Machine-readable source:
`contracts/governance-intelligence/compatibility-policy.json`.

## Verify locally

Run the dedicated gate:

```bash
uv run python scripts/verify_governance_intelligence_contract_evolution.py
```

Run it together with the artifact/consumer proof:

```bash
uv run python scripts/quality_gate.py \
  --check governance-intelligence-evolution \
  --check governance-intelligence-compatibility
```

Expected output:

```text
[ph-2] schema=1.0 status=current read=1.0 digest=... PASS
[ph-2] PASSED current=1.0 supported=1
```

## Adding a minor version

Use a new minor only for advisory evolution that preserves existing meaning:

1. leave every existing model and snapshot unchanged;
2. add a dedicated new envelope/model implementation;
3. add the new model to the public dispatch registry;
4. generate a new, separately named JSON Schema snapshot;
5. add at least one explicit-version example;
6. append an ordered manifest record, make it `current` and move the previous current record to
   `supported` or `deprecated`;
7. declare the new version readable with every earlier supported minor in the same major;
8. update consumer compatibility evidence, contract documentation and package release notes;
9. run the full repository gate and the two external consumer probes.

Do not add a field to the existing v1.0 model and then regenerate `v1.schema.json`.

## Adding a major version

A new major is required for removed/renamed fields, newly required data, narrower validation,
changed field meaning or changed structural interpretation. In addition to the minor-version steps:

- document why a non-breaking design is insufficient;
- define producer selection and consumer migration explicitly;
- decide whether cross-major read compatibility is implemented or intentionally absent;
- preserve the prior major while any supported consumer still needs it;
- provide version-specific transformation only if its semantics can be deterministic and tested.

Changing the advisory trust boundary is not a major-version operation. Authority fields and trusted
agent conclusions remain prohibited by ADR 0054.

## Deprecating or removing a version

Deprecation changes the manifest status but keeps the model, snapshot, fixtures and dispatch active.
Record consumer evidence and release communication outside the wire payload; do not inject warnings
or migration metadata into findings.

Removal deletes support and is a breaking release decision. Before removal:

- prove that active consumers no longer emit or require the version;
- update cross-repository fixtures/checkouts;
- publish release and migration notes;
- review retention/audit requirements for historical payloads;
- keep an offline verification strategy for retained evidence where required.

## Generating a snapshot

The checked-in representation uses sorted, indented JSON plus a final newline. Generate a candidate
for a **new** model, review the semantic diff, and calculate the SHA-256 over the exact committed
bytes. Then add the digest to the new manifest record.

The gate checks both digest and semantic equality with `model_json_schema()`. Updating the digest
cannot make an overwritten old version pass.

## Failure triage

| Failure | Meaning |
|---|---|
| policy field/status/version error | manifest is ambiguous or outside the closed PH-2 format |
| registry differs from policy | shipped dispatch and declared support disagree |
| current version mismatch | producer default and manifest current version disagree |
| digest drift | snapshot bytes changed without the declared immutable artifact |
| model/snapshot mismatch | model semantics changed without a new version |
| example failure | supported fixture no longer validates under its immutable model |
| prior same-major version missing from `read_compatible_with` | backward-reader guarantee would be broken |

Never resolve a failure by making the generic parser guess a version, allowing extras, or deleting
an old manifest record without the explicit removal process.

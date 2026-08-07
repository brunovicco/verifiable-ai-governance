# ADR 0026 - Canonical and idempotent demo seed

## Status

Accepted.

## Date

2026-08-06.

## Context

The repository already contained a useful gallery seed with ten initiatives
covering multiple lifecycle states. That script intentionally aborted when any
`[DEMO]` initiative existed and required recreating the PostgreSQL volume before
rerunning.

The gallery is valuable for broad UI coverage, but it does not provide one
coherent business narrative across initiative, assessments, approvals, evidence,
system, models, agent, runtime decisions and incident response. Its disconnected
examples also make screenshots, interviews and future cross-repository integration
harder to reproduce.

A portfolio demo needs a stable story with explicit expected states. Repeated
execution must not duplicate records, and partial state must not be silently
repaired because doing so can conceal schema, service or policy regressions.

## Decision

- add one canonical corporate-credit scenario under a distinct
  `[DEMO-CANONICAL]` marker;
- keep the existing ten-case seed as a separate gallery command;
- use real initiative, assessment, inventory, routing, incident and audit
  application services when creating the canonical scenario;
- keep the credit decision deterministic and restrict the LLM role to drafting a
  narrative opinion;
- create one independently reviewed model and one deliberately unreviewed model;
- create an agent allowlist containing only the reviewed model;
- persist one allowed routing decision and one accepted-but-locally-blocked
  out-of-scope group decision;
- open and contain a runtime incident from the blocked decision, then attach a
  remediation plan;
- seed no prompts, documents, credentials or personal data;
- treat reruns as validation: return success for a complete matching scenario and
  fail closed for partial or inconsistent state;
- expose an explicit destructive reset only for non-production, requiring the
  exact confirmation phrase;
- make reset clear all application tables, including audit events, because
  deleting selected events would invalidate the hash chain;
- write a runtime manifest with generated entity identifiers after successful
  creation or validation.

## Why reset clears all application data

Audit events are hash chained. Removing only events associated with demo entities
would break every later hash that depends on them. Rewriting the surviving chain
would alter non-demo evidence and would be architecturally unacceptable.

Therefore reset is intentionally a whole-application operation for a dedicated
demo database. It is not a general-purpose cleanup command and is blocked in
production.

## Alternatives considered

- Expand the ten-case gallery with more records: rejected because it improves
  breadth but not narrative coherence or idempotency.
- Silently upsert every entity: rejected because service-generated IDs,
  immutable audit events and material review state make generic repair unsafe.
- Delete only canonical records on reset: rejected because associated audit-event
  deletion would invalidate the remaining hash chain.
- Hard-code all generated entity UUIDs: rejected because existing application
  services own entity creation and should remain the exercised path.
- Seed through HTTP endpoints: deferred because authentication and network setup
  add fragility without improving the domain coverage of this delivery.
- Call the real external Policy Model Router during seed: deferred to Phase 2;
  P0.3 must work offline and reproducibly.
- Engage the kill switch in the default seed: rejected for P0.3 because full
  cross-component kill-switch enforcement is a later runtime-integration item.

## Consequences

- `make seed-demo` now means the canonical story;
- `make seed-demo-gallery` preserves the historical UI-coverage dataset;
- a partially seeded canonical scenario causes a visible non-zero exit instead of
  producing mixed or misleading data;
- generated IDs remain stable across idempotent reruns, but change after an
  explicit full reset;
- task identifiers, scenario version, control IDs and expected outcomes remain
  stable and can anchor screenshots and E2E tests;
- the deterministic demo router stub must never be used as a production adapter.

## Security and privacy impact

The scenario uses synthetic names and content-minimized URNs. Runtime evidence
contains IDs, policy provenance, constraints, outcomes and reason codes, not prompt
or response content.

Reset is guarded by environment and an exact phrase. Operators must still use a
dedicated database: non-production does not mean disposable.

The agent receives no credit-approval permission. Its allowed tools are read-only,
and the seeded human approval points make the authority boundary explicit.

## Operational impact

The seed requires a migrated database. It can run without MinIO, ClamAV or an
external router because evidence is reference-based and routing uses an in-process
deterministic test double.

Successful runs write:

```text
artifacts/demo/canonical-seed-manifest.json
```

`make seed-demo-check` is suitable for deployment smoke tests after migration and
seeding.

## Follow-up

- use the canonical task and workflow IDs in the integrated E2E test;
- replace the deterministic router test double with the real Policy Model Router
  in Phase 2;
- propagate trace and correlation IDs through the Credit Desk and a2a-otel-kit;
- add signed authorization and scope-digest invalidation;
- add real violation-event ingestion and kill-switch enforcement;
- update screenshots and the five-minute demo script around this scenario.

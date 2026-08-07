# Canonical demo scenario — governed corporate credit runtime

## Business story

A corporate-credit desk needs to accelerate analysis without transferring
approval authority to a language model.

The deterministic credit core calculates financial indicators, policy results,
rating and limit recommendations. The governed agent receives only structured,
minimized facts and may draft a narrative opinion. A human approver remains the
final decision authority.

The scenario is intentionally designed to connect later with:

```text
Verifiable AI Governance
    -> Policy Model Router
    -> Multi-Agent Credit Desk
    -> a2a-otel-kit
    -> Verifiable AI Governance
```

P0.3 seeds the Governance side of that story and produces runtime-routing evidence
through the enforcement logic already implemented in this repository.

## Canonical entities

| Entity | Canonical value | Expected state |
|---|---|---|
| Initiative | `[DEMO-CANONICAL] Análise de Crédito PJ Assistida e Auditável` | Approved |
| AI system | `Mesa de Crédito PJ Governada` | Active |
| Approved model | `credit-opinion-approved` | Independently reviewed |
| Out-of-scope model | `credit-opinion-experimental` | Draft and not reviewed |
| Agent | `Agente de Parecer de Crédito PJ` | Independently reviewed |
| Runtime incident | `Tentativa bloqueada de uso de modelo fora do escopo` | Remediating |

## Authority boundary

The agent:

- may read deterministic credit-analysis facts;
- may draft a narrative opinion;
- may not calculate the rating;
- may not alter limits or guarantees;
- may not approve credit;
- may not invoke transactional tools;
- may use only the reviewed model in its allowlist.

The system metadata records `human_credit_approver` as the decision authority and
`opinion_drafting_only` as the LLM role.

## Seeded controls

- `GOV-HUM-001` — human oversight;
- `GOV-MOD-003` — approved-model enforcement;
- `GOV-AGT-002` — tool and MCP allowlist;
- `GOV-AGT-004` — human approval for material actions;
- `GOV-OPS-001` — runtime monitoring;
- `GOV-EVD-001` — integrity-preserving audit trail;
- `GOV-EVD-002` — independent evidence and evaluation.

The IDs come from the repository's actual declarative control catalog.

## Assessments and evidence

The seed creates and submits:

1. AI Impact Assessment;
2. RIPD;
3. International Processing Assessment.

It also creates content-minimized references for all current evidence categories:

- architecture;
- policy;
- assessment;
- security test;
- approval;
- other/runbook.

References use `urn:demo:` identifiers. No customer documents, prompts,
credentials or personal data are seeded.

## Runtime decisions

Both attempts use workload `opinion_drafting` and the same approved agent scope.

### Authorized attempt

```text
task_id = draft-opinion-authorized-model
selected group = credit-opinion-approved
expected outcome = allowed
```

### Unauthorized attempt

```text
task_id = draft-opinion-unapproved-model
selected group = credit-opinion-experimental
expected outcome = blocked
reason_code = selected_model_group_not_approved
```

The second attempt is blocked after the simulated Policy Model Router decision and
before inference. Its structured evidence becomes the source for the seeded
incident.

The local deterministic router stub exists only to make this seed reproducible.
It does not replace the real Policy Model Router integration planned for Phase 2.

## Idempotency

Running `make seed-demo`:

- creates the scenario when absent;
- validates and returns success when the complete scenario already exists;
- fails closed when a partial or inconsistent scenario is found;
- never silently repairs material drift.

A runtime manifest is written to:

```text
artifacts/demo/canonical-seed-manifest.json
```

## Commands

```bash
make migrate
make seed-demo
make seed-demo-check
```

Explicit reset for a dedicated non-production demo database:

```bash
make seed-demo-reset
```

Reset deletes **all application data**, including the audit chain, before
reseeding. It:

- requires the exact confirmation phrase;
- is disabled when `APP_ENV=production`;
- must not be used on a shared development, staging or corporate database.

The historical ten-case gallery remains available separately:

```bash
make seed-demo-gallery
```

Do not run the gallery and canonical seed against the same database when preparing
screenshots or the five-minute portfolio demonstration.

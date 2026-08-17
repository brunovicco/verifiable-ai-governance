# GI-2/GI-2A governed advisory analysis

- **Status:** Current
- **Owner:** Platform engineering, security and AI Governance
- **Last reviewed:** 2026-08-17
- **Review trigger:** Analysis purpose, source, audit, provider or consumer change
- **Authoritative sources:** ADR 0059 and the GI-2 application tests

GI-2 defines the application boundary between verified Governance Knowledge and an untrusted
Governance Intelligence adapter. GI-2A composes that boundary with deployment-owned limits and its
request-scoped audit unit. Neither increment exposes an endpoint nor configures a provider.

## Internal composition

`build_governance_intelligence_analysis` accepts a governed knowledge resolver and an explicitly
supplied `GovernanceIntelligencePort`. It constructs `RunGovernanceIntelligenceAnalysis` with one
new `SqlAlchemyGovernanceIntelligenceAudit` instance used for both audit append and transaction
control. Never split those two ports across different instances: the adapter deliberately permits
only one active audit-stage transaction.

The builder is not a FastAPI dependency and has no registered route, task or scheduler. Merely
configuring its limits does not enable analysis, choose a model or create network egress.

## Deployment policy

| Environment variable | Default | Accepted range | Purpose |
|---|---:|---:|---|
| `GOVERNANCE_KNOWLEDGE_MAX_SOURCES` | `10` | `1..100` | Shared GI-1/GI-2 complete-set source limit |
| `GOVERNANCE_INTELLIGENCE_MAX_FINDINGS` | `10` | `1..100` | Maximum complete candidate set before release |
| `GOVERNANCE_INTELLIGENCE_ANALYSIS_TIMEOUT_SECONDS` | `30` | `> 0..300` | Maximum advisory execution time in seconds |

Settings validation fails closed outside these ranges. A future provider must still define shorter
or equal transport connection/read timeouts, bounded retries and cancellation behavior; this
application timeout is not a transport policy.

## Guaranteed sequence

```text
analysis_requested audit committed
  → GI-1 complete-set authorization and actual-byte verification
  → sources_verified audit committed
  → one explicit advisory port operation under a bounded timeout
  → candidate schema, purpose, citation and provenance validation
  → terminal audit committed
  → versioned advisory envelopes returned
```

If an audit stage cannot be committed, the next sensitive stage does not run. Findings are not
released unless the completion event is durable.

## Explicit purposes

| Purpose | Port operation | Allowed findings |
|---|---|---|
| `policy_analysis` | `analyze_policy` | `policy_interpretation`, `evidence_gap` |
| `risk_identification` | `identify_risks` | `risk_candidate`, `evidence_gap` |
| `control_suggestion` | `suggest_controls` | `control_candidate`, `evidence_gap` |
| `evidence_analysis` | `analyze_evidence` | `evidence_interpretation`, `evidence_gap` |
| `intake_assistance` | `assist_intake` | `intake_suggestion`, `evidence_gap` |

These operations cannot approve, authorize, sign, release, change runtime policy or mutate governed
records.

## Output acceptance rules

- source references are schema-revalidated and bounded before request audit is written;
- output must be a tuple no larger than the constructor-supplied `max_findings` limit;
- each item must survive fresh `GovernanceFindingCandidate` schema validation;
- finding IDs, candidate citations and provenance sources must not be duplicated;
- candidate type must be allowed for the explicit purpose;
- provenance correlation ID must match the authenticated access context;
- provenance retrieval sources must equal the complete verified input set;
- candidate citations must be a subset of that set;
- the complete output is accepted or rejected together.

An empty tuple is a valid advisory result. Confidence never grants authority.

## Audit stages

| Stage | Sequence | Meaning |
|---|---:|---|
| `analysis_requested` | 1 | Purpose and requested content-free references were recorded before source access |
| `source_resolution_failed` | 2 | GI-1 failed without releasing a source set |
| `sources_verified` | 2 | The complete authorized source set passed actual-byte verification |
| `analysis_completed` | 3 | All candidates passed validation, including an empty result |
| `analysis_rejected` | 3 | Untrusted output failed schema, purpose, citation, provenance or count policy |
| `analysis_dependency_failed` | 3 | The adapter failed or exceeded the bounded timeout |

Audit payloads may contain source IDs, versions, digests, finding IDs/types, agent-run IDs, byte
counts and failure categories. They must not contain source content, filenames, bucket/key/URI,
finding statements, prompts, chain-of-thought or raw provider responses.

Cancellation propagates. If cancellation occurs during source or analysis work, an existing
requested or sources-verified event without a terminal event is the durable interrupted-execution
signal.

## Failure triage

| Public failure | Check |
|---|---|
| GI-1 `source_unavailable` | actor/subject authorization, exact source identity and metadata |
| GI-1 `integrity_mismatch` | persisted digest versus actual object bytes |
| `dependency_unavailable` before source access | audit database/transaction availability |
| `dependency_unavailable` after source verification | adapter dependency, timeout or terminal audit commit |
| `output_rejected` | schema, allowed type, correlation, citations and provenance source set |
| `limit_exceeded` | configured maximum findings returned by the adapter |

Do not log or persist rejected payloads while investigating. Reproduce with synthetic content and
the content-free correlation ID.

## Verify locally

```bash
uv run pytest -q \
  apps/api/tests/test_governance_intelligence_application.py \
  apps/api/tests/test_governance_intelligence_contract.py \
  apps/api/tests/test_governance_knowledge_application.py \
  apps/api/tests/test_governance_knowledge_evidence_adapter.py \
  apps/api/tests/test_architecture.py
```

Run the complete repository gate before merging:

```bash
uv run python scripts/quality_gate.py
```

## Before adding a provider or consumer

1. supply the provider only through `GovernanceIntelligencePort` to the existing composition-root
   builder;
2. preserve its single request-scoped `SqlAlchemyGovernanceIntelligenceAudit` instance for both
   audit and transaction ports;
3. review the shared source limit, finding limit and analysis timeout for the intended workload;
4. configure transport connection/read timeouts and bounded retry behavior;
5. verify authenticated actor, subject and administrator mapping at the delivery boundary;
6. document data classification, purpose and provider/model egress;
7. define credentials, regional processing, retention and deletion policy;
8. add rate, concurrency, cost and abuse limits;
9. test provider failures, malformed output, cancellation and audit outages;
10. keep findings advisory and route any accepted recommendation through an existing governed
   human or deterministic decision path.

Correlation IDs are trace identifiers, not idempotency keys. GI-2 persists neither findings nor
agent-run records and makes no claim of replay suppression.

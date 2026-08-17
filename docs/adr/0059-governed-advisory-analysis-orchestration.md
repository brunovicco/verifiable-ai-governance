# ADR 0059 - Governed advisory analysis orchestration

- **Status:** Accepted
- **Date:** 2026-08-17
- **Decision owners:** Engineering, architecture, security and AI Governance

## Context

GI-0 defined closed, non-authoritative finding contracts and a consumer-owned
`GovernanceIntelligencePort`. GI-1 established authorization, exact-version resolution, bounded
reads and actual-byte digest verification. GI-1A connected that gate to clean, trusted private
evidence uploads.

Those boundaries still did not define how a caller may combine verified sources with an untrusted
analysis adapter. Calling the port directly would leave content-access audit timing, purpose,
timeouts, output cardinality, citation binding and provenance consistency to every integration.
That would make it easy for a future model or agent adapter to cite sources it did not receive,
return an inappropriate finding type, or release results without durable access evidence.

## Decision

### Application-owned orchestration

`RunGovernanceIntelligenceAnalysis` is the only application use case introduced by GI-2. It accepts:

- one explicit `GovernanceIntelligenceAnalysisType`;
- exact `GovernanceSourceReference` values;
- authenticated `GovernanceKnowledgeAccess`;
- explicit maximum-finding and analysis-timeout limits.

It coordinates existing ports in this order:

```text
commit analysis_requested audit
  → authorize, resolve and digest-verify the complete source set
  → commit sources_verified audit
  → invoke one advisory GovernanceIntelligencePort operation with verified sources
  → revalidate and source-bind every candidate
  → commit terminal audit outcome
  → release versioned advisory envelopes
```

The concrete audit adapter implements both audit and transaction ports with a dedicated,
short-lived SQLAlchemy session for each stage, so its commits cannot include caller-owned changes
and no audit transaction remains open while object storage or an analysis adapter is running.
Concrete knowledge adapters must still bound their own metadata-read transaction lifetime. An audit
append or commit failure stops the next sensitive stage. A completion-audit failure withholds
otherwise valid findings.

### Explicit purpose and finding types

The allowed operation and output taxonomy is closed:

| Analysis type | Port method | Allowed primary finding type |
|---|---|---|
| `policy_analysis` | `analyze_policy` | `policy_interpretation` |
| `risk_identification` | `identify_risks` | `risk_candidate` |
| `control_suggestion` | `suggest_controls` | `control_candidate` |
| `evidence_analysis` | `analyze_evidence` | `evidence_interpretation` |
| `intake_assistance` | `assist_intake` | `intake_suggestion` |

`evidence_gap` is permitted for every purpose. No approval, authorization, signing, runtime-control
or governed-state operation is available.

### Output validation

Analysis output remains untrusted even when the port is typed. Before release, the application:

- revalidates and limits the source-reference tuple before writing request audit metadata;
- requires a finding tuple within a configured maximum between 1 and 100;
- revalidates every candidate through the closed shared schema;
- rejects duplicate finding IDs and duplicate source references;
- requires the finding type to match the requested purpose;
- requires provenance correlation to match the authenticated access context;
- requires provenance `retrieved_sources` to equal the complete verified input set;
- requires every cited source to be a subset of that verified set;
- wraps accepted candidates in the current `GovernanceFindingEnvelope`.

An empty result is valid and is still audited. Invalid output is rejected as a complete set; no
partial finding is released.

### Audit minimization and sequencing

GI-2 reuses the append-only hash-chained `AuditEvent` store and introduces no table or migration.
The SQLAlchemy adapter records only:

- actor, subject, correlation ID, administrator-access assertion and explicit analysis purpose;
- exact content-free source references and aggregate verified byte count;
- terminal stage and bounded failure reason;
- accepted finding IDs, types and agent-run IDs.

It never records source bytes, filenames, object-storage coordinates, finding statements,
confidence explanations, prompts, chain-of-thought, tool output or complete model responses.

The lifecycle contains `analysis_requested`, either `source_resolution_failed` or
`sources_verified`, and then a completed, rejected or dependency-failed terminal event when the
analysis stage runs. Cancellation propagates normally. A durable requested/verified event without
a terminal event identifies an interrupted execution without delaying cancellation to write a new
event.

Correlation IDs provide traceability, not idempotency. GI-2 does not persist an agent run or finding
record and does not claim replay suppression.

### Failure and timeout behavior

Knowledge failures retain the existing GI-1 content-free reasons. Analysis dependency failures and
timeouts become `dependency_unavailable`; structurally or semantically invalid candidates become
`output_rejected`; excess findings become `limit_exceeded`.

Source count and finding count limits are mandatory and each constrained between 1 and 100.
Analysis timeout is mandatory and constrained to more than zero and at most 300 seconds. Concrete
provider adapters must still configure transport connection/read timeouts, retry policy and
cancellation behavior appropriate to their dependency.

### Internal composition policy

GI-2A adds one composition-root builder for the existing use case. The builder accepts an already
governed knowledge resolver and an explicitly supplied `GovernanceIntelligencePort`; it does not
select or instantiate a provider. It applies deployment policy from `Settings`:

- `GOVERNANCE_KNOWLEDGE_MAX_SOURCES` is reused as the complete-set source-count limit, so GI-1 and
  GI-2 cannot silently disagree about request cardinality;
- `GOVERNANCE_INTELLIGENCE_MAX_FINDINGS` bounds the complete candidate set;
- `GOVERNANCE_INTELLIGENCE_ANALYSIS_TIMEOUT_SECONDS` bounds advisory execution independently from
  any future provider transport timeout.

Invalid values fail during settings validation. The builder creates exactly one request-scoped
`SqlAlchemyGovernanceIntelligenceAudit` and supplies that same object as both audit and transaction
port. This preserves the adapter's one-stage-at-a-time unit-of-work invariant. Container defaults
are explicit, but there is no enable flag because no consumer path exists.

### Exposure boundary

GI-2/GI-2A add no HTTP endpoint, FastAPI dependency, task, scheduler, provider adapter, model call,
retrieval engine, prompt, finding persistence or governed decision transition. The internal
composition remains inert until a separately reviewed consumer supplies a concrete
`GovernanceIntelligencePort`.

Before that consumer is exposed, it still requires provider/model egress, data-classification,
retention, rate-limit, credential, reviewer-access and abuse-case review. The existing verified
evidence adapter is not automatically connected to any model or external destination.

## Consequences

### Positive

- future adapters cannot bypass verified source resolution through the governed use case;
- source access is durably recorded before verified bytes reach an analysis adapter;
- hallucinated citations, mismatched provenance and purpose-inappropriate finding types fail closed;
- audit metadata supports independent tracing without retaining content or model responses;
- timeout, cancellation and all-or-nothing result behavior are executable application policy;
- composition applies one fail-closed deployment policy and one audit unit of work without choosing
  a provider;
- the deterministic governance core and runtime authority paths remain unchanged.

### Costs and follow-ups

- each analysis lifecycle writes up to three short audit transactions;
- verified bytes remain in memory within the existing GI-1 limits during analysis;
- correlation IDs are not durable idempotency keys;
- a concrete provider adapter and production consumer still require separate security review;
- accepted finding content remains ephemeral; GI-3 can record a minimized digest-bound review
  receipt, but a future product decision must still define queues, retention and delivery behavior.

## Rejected alternatives

### Let each provider adapter orchestrate source access and auditing

Rejected. Authorization, audit ordering, output binding and failure policy are application
concerns and must remain consistent across providers.

### Trust typed `GovernanceFindingCandidate` instances without revalidation

Rejected. Python typing is not a runtime trust boundary, and unchecked construction or adapter bugs
could bypass normal schema parsing.

### Allow candidates to cite any well-formed source reference

Rejected. Shape validation does not prove that a source was authorized, resolved or supplied to
the analysis operation.

### Persist findings and model responses now

Rejected. Retention, reviewer workflow, data minimization and lifecycle requirements are not yet
decided. Audit identities are sufficient for this boundary.

### Add an HTTP endpoint or provider adapter with the orchestration

Rejected. The deterministic consumer boundary must be reviewable before credentials, egress,
prompts or probabilistic execution are introduced.

### Treat successful analysis as a governance decision

Rejected. Every returned envelope remains untrusted and advisory. Only existing human or
deterministic governed use cases may change authoritative state.

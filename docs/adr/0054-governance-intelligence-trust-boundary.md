# ADR 0054 - Governance Intelligence trust boundary and advisory finding contracts

- **Status:** Accepted
- **Date:** 2026-08-16
- **Decision owners:** Engineering, architecture and AI Governance

## Context

The stabilized runtime-governance path is the platform trust anchor:

```text
Policy
  → Risk
  → Control
  → Approval
  → Signed Runtime Authorization
  → Runtime Enforcement
  → Runtime Violation / Telemetry
  → Runtime Assurance
  → Governed Response
  → Evidence
  → Audit
```

Future Governance Intelligence capabilities may use agents, retrieval, models or external systems
to interpret policy, identify possible risks, suggest controls, identify evidence gaps and assist
intake. Those capabilities are useful only if they remain upstream of the deterministic governance
core and cannot acquire governance authority through a convenient integration interface.

The invariant is:

```text
Agents reason.
Governed systems decide.
Runtime evidence proves.
```

## Problem

Without a contract and explicit trust boundary, a structurally valid model or tool response could
be mistaken for an approved risk, control, compliance conclusion or runtime authorization. Direct
framework imports in the application core could also allow provider-specific behavior to shape the
authority model before validation and review rules exist.

GI-0 must establish portable advisory contracts and a consumer-owned application port without
introducing model execution, retrieval, persistence or changes to the existing governance and
runtime paths.

## Decision

### Authority model

Governance Intelligence is **advisory, untrusted and non-authoritative**. Its outputs cannot approve
systems or controls, declare compliance, alter governed decisions, sign authorizations, expand
scope, modify runtime policy, operate the kill switch, restore runtime or release models or tools.

Only existing deterministic application/domain use cases may create governed decisions. Runtime
enforcement is authoritative only within the scope and lifetime of a verified signed authorization.
Evidence remains a verifiable source artifact or proof; a generated interpretation is derived data,
not evidence.

### Trust boundary

LLM output, external findings, retrieved content, uploaded documents and tool output enter as
untrusted data. Before a candidate can be presented for review, its envelope must pass schema
validation and its source references must be resolved and checked against the identified artifact
versions and digests. Schema-valid data still does not become a governance decision.

```text
Untrusted model, retrieval, document, tool or external output
  → closed schema validation
  → source validation and reference resolution
  → digest verification
  → GovernanceFindingCandidate (still advisory and untrusted)
  → human or deterministic review
  → governed decision through an existing authoritative use case
```

### Advisory contracts

The vendor-neutral `governance-schemas` package owns:

- `GovernanceFindingEnvelope`, the versioned wire wrapper;
- `GovernanceFindingCandidate`, the advisory conclusion and confidence;
- `GovernanceSourceReference`, a content-free locator bound to artifact version and digest;
- `ExternalTaxonomyReference`, a generic provider/taxonomy locator;
- `AgentRunProvenance`, bounded audit context without prompt or reasoning content;
- `GovernanceFindingType`, a small initial finding taxonomy.

Contract models are immutable and closed with Pydantic `extra="forbid"`. The candidate fixes
`trust_level` to `untrusted` and `advisory_only` to `true`. Confidence is bounded to `[0, 1]`, but
even `1.0` carries no authority. Unexpected fields such as `approved`, `authorized` or `compliant`
are rejected rather than ignored.

The finding taxonomy is intentionally limited to policy interpretation, risk and control
candidates, evidence gaps and interpretations, and intake suggestions. Adding authority outcomes
is not a taxonomy extension; it requires a separate governed decision path.

### Source references and evidence

`GovernanceSourceReference` identifies an artifact, its version, an optional node/section and the
SHA-256 digest of the referenced version. It does not carry document content. Resolution,
authorization to read, authenticity assessment and digest verification occur outside the data
model.

An AI-generated interpretation is not evidence. The original artifact is the referenced source;
the finding is a derived representation that a reviewer may accept, reject or ignore.

`ExternalTaxonomyReference` represents provider, taxonomy, identifier, version and optional URI
without coupling the core to NIST, OWASP, MITRE, EU, ASAGO, a GRC or an internal framework.

### Agent-run provenance

`AgentRunProvenance` records the run and agent identifiers, provider/model identity, prompt
configuration version, optional retrieval-query and tool-call references, retrieved source
locators, a UTC timestamp and correlation ID. It deliberately has no chain-of-thought, full prompt,
document body or complete model-response field.

### Application port

`GovernanceIntelligencePort` is a consumer-owned `Protocol` in the application layer. It exposes
only analysis operations for policy, risks, controls, evidence and intake and returns
`GovernanceFindingCandidate` values. Inputs are stable subject IDs and versioned source references;
provider and retrieval implementation details remain behind future adapters.

The port has no approval, authorization, signing, scope mutation, release, kill-switch or restore
methods. Architecture tests protect both that negative capability surface and the absence of direct
imports from `langgraph`, `deepagents`, `openai`, `anthropic`, `asago` and `langchain`.

### Forbidden dependencies and scope

The Governance Intelligence application core does not depend on an agent framework, model
provider, retrieval product, vector database, external taxonomy system or observability vendor.
GI-0 adds no adapter, model call, prompt, retrieval pipeline, persistence, table or migration and
does not change runtime enforcement, approvals, signing, Policy Model Router or Runtime Assurance.

## Consequences

### Positive

- future probabilistic integrations have a narrow, portable advisory output contract;
- authority escalation is rejected structurally and protected by negative tests;
- source and run provenance can be reviewed without copying sensitive content into the contract;
- provider/framework choices remain adapter decisions rather than application-core dependencies;
- the deterministic governance and runtime trust anchors remain unchanged.

### Costs

- future adapters must resolve and verify source references before presenting candidates;
- schema evolution and cross-repository compatibility require explicit version discipline;
- a human or deterministic review step remains necessary even for high-confidence findings;
- provider-specific metadata that does not fit the minimal contract must remain outside the core or
  motivate a separately reviewed contract revision.

## Rejected alternatives

### Allow agents to write directly to governed models

Rejected. This would let an untrusted reasoning system bypass authoritative application/domain use
cases and their segregation-of-duties, audit and validation rules.

### Let agent output represent approval or compliance

Rejected. Structured output and confidence do not establish authorization, reviewer independence,
legal sufficiency or compliance.

### Couple the core directly to LangGraph or another agent framework

Rejected. Orchestration is an adapter concern and cannot define the governance authority model.

### Couple the core directly to ASAGO

Rejected. External taxonomies and GRC systems are referenced generically and never become the core
domain authority.

### Create provider-specific LLM contracts

Rejected. Findings must remain portable across providers and usable by non-LLM external systems.

### Treat retrieved knowledge as evidence

Rejected. Retrieval produces a reference and interpretation; the original resolved artifact is the
potential evidence and still requires integrity, authenticity, validity and scope assessment.

### Connect an LLM before defining the boundary

Rejected. Executing a probabilistic integration first would let implementation convenience decide
the trust and authority model implicitly.

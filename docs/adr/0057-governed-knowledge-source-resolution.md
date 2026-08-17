# ADR 0057 - Governed knowledge source resolution and integrity gate

- **Status:** Accepted
- **Date:** 2026-08-17
- **Decision owners:** Engineering, architecture and AI Governance

## Context

ADR 0054 established `GovernanceSourceReference` as a content-free locator for an exact artifact
version and SHA-256 digest. ADRs 0055 and 0056 protect the portability and evolution of the finding
contract. A validated reference still does not prove that the identified source exists, that the
requester may read it, or that the resolved bytes match the declared version and digest.

Passing raw references directly to a future model, retrieval system or external analysis adapter
would let infrastructure convenience bypass the trust boundary. GI-1 therefore needs a
deterministic knowledge gate before any probabilistic or retrieval integration is connected.

## Decision

### Consumer-owned source boundary

The application layer owns two provider-neutral ports:

- `GovernanceKnowledgeAuthorizerPort` decides whether an authenticated actor may resolve an exact
  reference for one governed subject;
- `GovernanceKnowledgeResolverPort` returns an unverified, bounded-read source stream for the exact
  artifact identity and version without interpreting content.

Authorization receives `GovernanceKnowledgeAccess`, which binds actor, governed subject and
correlation identity. A denial and an absent source produce the same content-free public failure so
the failure payload does not reveal whether a source exists. Dependency failures remain distinct
for operations but disclose no source metadata or content. Concrete adapters must also address
timing and transport side channels appropriate to their source system.

Authorization and resolution adapters remain responsible for their own infrastructure controls.
They cannot declare bytes verified; only the application use case can release a
`VerifiedGovernanceKnowledgeSource`.

### Deterministic verification gate

`ResolveGovernanceKnowledgeSources` performs the following sequence:

```text
closed GovernanceSourceReference
  → exact-reference authorization
  → exact artifact/version resolution
  → bounded streaming read
  → actual SHA-256 calculation
  → constant-time digest comparison
  → VerifiedGovernanceKnowledgeSource
  → future retrieval or analysis adapter
```

The use case rejects empty and oversized requests, exact duplicates, conflicting digests for the
same artifact version, identity/version mismatches, unsafe content-type metadata, empty content,
oversized sources and digest mismatches. Streams are closed whether verification succeeds or fails.

Batch resolution is all-or-nothing. No verified tuple is returned if any requested source fails.
Repeated node or section references to the same artifact version and digest are authorized
individually but reuse the same verified immutable bytes and count once toward the total byte
limit.

### Verified-only intelligence input

`GovernanceIntelligencePort` accepts `VerifiedGovernanceKnowledgeSource` values instead of raw
`GovernanceSourceReference` values. This makes source authorization and integrity verification an
application-level prerequisite for future agent, model or retrieval adapters.

The verified wrapper contains the original reference, bounded content type, byte count and
ephemeral immutable bytes. Its constructor rejects calls without the gate's private verification
token, and content is excluded from its representation. GI-1 does not persist, index, log, embed or
transmit those bytes and does not add an endpoint or composition-root binding. A future concrete
source adapter must receive a separate security and data-minimization review.

### Evidence and authority remain unchanged

Digest verification proves that the resolved bytes match the requested reference. It does not
prove authenticity, legal applicability, correctness, sufficiency or the truth of an
interpretation. Verified knowledge is not automatically governance evidence, and a finding derived
from it remains untrusted, advisory and non-authoritative.

GI-1 adds no approval, authorization, compliance, signing, runtime-control or governed-state
transition. It changes neither the Governance Finding wire schema nor its `1.0` snapshot.

### Limits and failure behavior

Source count, per-source bytes and aggregate bytes are mandatory positive configuration supplied by
the composition root. The application reads fixed-size chunks and releases no partial result.
Stable failure reasons distinguish invalid request, unavailable source, source mismatch, integrity
mismatch, limit breach and dependency outage without including artifact IDs, digests or content.

## Consequences

### Positive

- future adapters cannot satisfy the typed intelligence port with raw, unresolved references;
- exact version and actual bytes are bound deterministically before content leaves the gate;
- authorization happens before source resolution and failure payloads do not distinguish denial
  from absence;
- resource limits and guaranteed stream cleanup bound failure behavior;
- the core remains independent from model, retrieval, vector-database and storage products.

### Costs

- every concrete knowledge source needs both authorization and resolution behavior;
- source bytes are temporarily buffered after bounded streaming verification so the verified value
  is immutable for downstream consumers;
- an adapter must map provider-specific identities and versions to the generic source contract;
- content authenticity and semantic suitability still require source-specific governance.

## Rejected alternatives

### Pass raw source references to analysis adapters

Rejected. A reference validates shape but does not establish access, existence, version identity or
content integrity.

### Trust a resolver-provided digest without reading the bytes

Rejected. Metadata can be stale, mismatched or controlled by the same failing dependency. The
application calculates SHA-256 over the actual resolved bytes.

### Return partial results when one source fails

Rejected. An adapter could reason from an incomplete source set without recognizing the missing
context. Callers must issue a new explicit request if partial analysis is acceptable.

### Couple GI-1 to S3, a vector database or the existing evidence tables

Rejected. Source authorization and resolution are ports. Storage- and evidence-specific behavior
belongs in separately reviewed adapters and must not define the application contract.

### Add retrieval, embeddings or model execution with the foundation

Rejected. The deterministic trust gate must exist and be testable before probabilistic or indexing
components are allowed to consume governed knowledge.

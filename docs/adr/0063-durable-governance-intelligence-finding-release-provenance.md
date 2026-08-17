# ADR 0063 - Durable Governance Intelligence finding release provenance

- **Status:** Accepted
- **Date:** 2026-08-17
- **Decision owners:** Engineering, architecture, security and AI Governance

## Context

GI-2 releases a `GovernanceFindingEnvelope` only after verified source access, bounded advisory
execution, closed-schema validation, citation/provenance checks and a committed
`analysis_completed` audit event. That event currently retains finding, type and agent-run
identities, but not a digest of the complete released envelope.

GI-3 independently reconstructs an envelope and binds its complete digest to a durable review
receipt. Shape validation and correlation matching do not prove that the submitted finding passed
the GI-2 release boundary. A future caller could therefore submit a fabricated but schema-valid
finding and create review evidence for it. ADR 0060 explicitly left preservation of the GI-2
release boundary as a prerequisite for delivery.

## Decision

GI-3C adds an application-owned, content-minimized release registry between analysis and review.
It remains internal and introduces no provider or delivery path.

A single application function calculates lowercase SHA-256 over the complete
`GovernanceFindingEnvelope` serialized as canonical sorted compact JSON. GI-2 and GI-3 must use
that function so release and review cannot drift to different digest algorithms.

For every validated GI-2 envelope, the application creates an immutable release record containing:

- generated non-nil `release_id` and release schema version `1.0`;
- finding schema version, finding ID, type and agent-run ID;
- canonical candidate-envelope digest;
- governed subject and correlation identities;
- UTC release time, record version and a release digest over every preceding fact.

`finding_id` is globally single-use in the release registry. A second analysis cannot bind the
same finding identity to another envelope or release. An exact repeated candidate is also rejected;
GI-2 has no request identity or replay contract, so silently treating a repeated analysis as replay
would invent idempotency semantics it does not have.

The concrete GI-2 SQLAlchemy unit of work inserts every release record and appends the
`analysis_completed` audit event in the same transaction. The completion event includes only the
minimized release identities and digests. A release insert, completion audit or commit failure
withholds the complete finding set. A unique finding collision is an `output_rejected` result, not
a successful release.

GI-3 receives a `GovernanceFindingReleaseVerifierPort`. Each review attempt follows this order:

1. reconstruct and validate the closed finding envelope and request context;
2. perform current actor/subject/finding-type authorization;
3. calculate the canonical envelope digest;
4. require an intact release record with the exact finding, run, digest, subject and correlation;
5. only then resolve or create the durable review receipt.

An absent or differently bound release is exposed as the existing content-free `invalid_request`.
Release-registry corruption or database unavailability is exposed as
`dependency_unavailable`. Exact review replay performs the release check again; a review request is
not a bearer capability and cannot bypass either current authorization or release provenance.

The release registry stores no statement, confidence, source reference or bytes, prompt,
provider/model identity, chain-of-thought, tool output, raw response, storage coordinate or
free-form rationale. The Governance Finding `1.0` wire contract and the review receipt `1.0`
contract remain unchanged.

## Alternatives considered

### Query `AuditEvent.payload` as the release registry

Rejected. Audit JSON is integrity evidence, not a typed application lookup with explicit schema,
uniqueness and bounded reconstruction. Cross-dialect JSON queries would also weaken deterministic
verification.

### Return a signed release token with every envelope

Rejected for this increment. It would introduce signing-key generation, distribution, rotation and
verification policy before a delivery format has been selected. The existing governed database is
the current trusted persistence boundary.

### Add release fields to Governance Finding `1.0`

Rejected. Release is consumer/application evidence, not producer output. Changing the immutable
portable finding would mix trust zones and require an unnecessary contract version.

### Accept any schema-valid finding at review

Rejected. Schema validity proves shape and closed advisory semantics, not that verified sources,
purpose binding and terminal GI-2 audit succeeded.

### Persist the complete released finding

Rejected. Exact provenance verification needs identity and digests only. Full content would decide
retention, access, deletion and safe-rendering policy before delivery requirements exist.

## Consequences

- a review can prove database-visible passage through GI-2 without retaining finding content;
- analysis and review share one canonical envelope digest implementation;
- a finding identity cannot be rebound across analyses;
- release evidence and completion audit cannot commit independently;
- review denial occurs before release lookup, avoiding an unauthorized existence oracle;
- exact review replay now depends on continued availability and integrity of release evidence;
- existing internal callers that construct findings directly must first execute the GI-2 boundary;
- each released finding adds one minimized row and bounded indexes.

## Security and privacy impact

The new registry reduces fabricated-finding audit pollution and makes the GI-2-to-GI-3 boundary
fail closed. Release digests are compared using constant-time equality after strict schema, UUID,
UTC and lowercase SHA-256 validation. Unique finding identity prevents ambiguous provenance under
concurrent analyses.

The registry duplicates only controlled metadata already needed for traceability and excludes all
finding and source content. Subject and correlation identifiers, timestamps and digests remain
controlled metadata and must follow database access, backup and retention policy. Digests establish
binding and integrity; they do not prove truth, authenticity, compliance or governance authority.

## Operational impact

Migration `0022` creates the append-only release registry and its uniqueness/check constraints.
The migration must run before code that persists or verifies releases. GI-2 completion adds one row
per released finding inside the existing terminal transaction; GI-3 adds one indexed release read
after authorization and before review receipt access.

Duplicate finding IDs fail closed and may indicate a provider identity bug, replayed analysis or a
concurrent collision. Operators must investigate with release/finding/run, subject, correlation and
digest metadata without logging finding payloads. Backups, restores and retention must keep release
records consistent with review receipts and audit evidence.

## Follow-up

- define review listing, supersession and response semantics before delivery exposure;
- define coordinated retention, legal hold, deletion and export for release, review and audit
  evidence;
- derive actor, subject, administrator and request identities from a trusted authenticated delivery
  boundary with rate, size, concurrency and abuse controls;
- evaluate cryptographically portable release attestations only if releases must cross the trusted
  database boundary;
- select and security-review any concrete provider, including egress, credentials, regional
  processing, transport timeouts, retries, cost and content policy;
- route accepted recommendations only through existing authoritative governed use cases.

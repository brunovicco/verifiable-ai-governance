# ADR 0058 - Verified evidence Governance Knowledge adapter

- **Status:** Accepted
- **Date:** 2026-08-17
- **Decision owners:** Engineering, architecture, security and AI Governance

## Context

ADR 0057 established an application-owned gate that authorizes, resolves and verifies exact source
bytes before Governance Intelligence can consume them. It deliberately introduced no concrete
source adapter. The platform already has one governed content class suitable for the first adapter:
uploaded evidence that passed type/signature validation, malware scanning, SHA-256 calculation and
private immutable object storage.

The adapter must not make every evidence row readable, expose storage coordinates, reinterpret a
matching digest as truth, or create a hidden path from evidence content to an LLM. It must preserve
the existing initiative ownership boundary and the verified-only GI-1 gate.

## Decision

### Eligible source class

Only evidence rows that are all of the following are eligible:

- marked as trusted platform uploads;
- recorded with `scan_status="clean"`;
- backed by complete private object-storage metadata;
- bound to the requested initiative;
- stored under the canonical application key `evidence/{initiative_id}/{evidence_id}`.

Legacy external URI references, untrusted rows, infected files, incomplete metadata and
non-canonical storage keys are not knowledge sources. This eligibility is enforced both by the
SQLAlchemy metadata reader and by the source adapter.

### Canonical source identity

A verified upload maps to the existing `GovernanceSourceReference` without changing its wire
schema:

```text
artifact_id     = "evidence:<canonical non-nil UUID>"
version         = str(EvidenceRecord.version)
content_digest  = EvidenceRecord.sha256
node_id         = null
section         = null
```

Uppercase, aliased, malformed and nil UUIDs are rejected. Uploaded files do not currently expose a
canonical fragment model, so node and section references fail closed rather than pretending that a
page or clause was resolved.

`governance_reference_for_evidence` is the single adapter-owned mapping from eligible evidence
metadata to this content-free reference. It does not include filename, storage bucket, key or URI.

### Authorization and subject isolation

`GovernanceKnowledgeAccess.subject_id` is the exact initiative ID. Access is allowed only when:

- the initiative exists;
- the authenticated actor is its business owner, or the trusted principal carries the existing
  governance-administrator assertion;
- the evidence belongs to that same initiative;
- identity, version and digest match the persisted metadata exactly.

The access context now carries `is_admin`, sourced from the existing authenticated `Principal`; it
is not inferred from evidence metadata or a request payload.

Authorization state is cached only in the request-scoped adapter instance and is keyed by actor,
subject, correlation ID, admin assertion and exact reference. Resolution without successful prior
authorization on that same instance returns no source. This prevents the resolver from becoming a
standalone private-object read API.

### Private object resolution

`S3ObjectStorage.open` opens only the configured bucket and the canonical key obtained from trusted
metadata. Bucket substitution fails before a network request. The streaming body is adapted to the
GI-1 bounded asynchronous content port; read, close and transport failures become content-free
dependency errors.

Connection/read timeouts and bounded standard retries remain controlled by the existing boto3
client configuration. The application gate applies source-count, per-source and aggregate byte
limits during reads and recalculates SHA-256 over the actual object bytes. S3 metadata is not
accepted as a substitute for actual-byte verification.

### Composition and exposure

The composition root creates one `VerifiedEvidenceKnowledgeAdapter` instance for both the
authorization and resolver ports, then wraps it with `ResolveGovernanceKnowledgeSources` and
explicit environment-backed limits.

GI-1A adds no HTTP endpoint, background job, retrieval index, model call, prompt, agent runtime or
content persistence. No current request path invokes the adapter. A future governed consumer must
define its own authorization-preserving API/use case, audit requirement, timeout/cancellation
tests, and content-egress review before production exposure.

### Evidence and authority remain distinct

An eligible uploaded artifact has platform-verified transport and integrity controls. Reading it
through this adapter does not establish that its claims are authentic, valid, sufficient,
effective or compliant. A Governance Intelligence interpretation remains a derived, untrusted,
advisory output and cannot mutate a decision or authorization.

## Consequences

### Positive

- GI-1 now has a concrete adapter over an already governed private source class;
- initiative ownership and administrator access remain fail-closed before object storage;
- exact metadata, canonical storage identity and actual bytes are independently checked;
- external URI evidence and unsafe fragment claims cannot enter this path;
- no new database schema, dependency, credential or network destination is introduced.

### Costs

- the adapter is deliberately limited to whole uploaded files;
- verified bytes are buffered only within the GI-1 configured limits;
- request-scoped authorization cache requires the same adapter instance on both ports;
- future production consumption still needs an explicit content-access audit decision.

## Rejected alternatives

### Resolve every evidence row with a URI

Rejected. External references have not passed the private upload and malware-verification pipeline
and must remain visibly distinct.

### Use the S3 URI or key as `artifact_id`

Rejected. Storage coordinates are private infrastructure details and can change independently from
the stable evidence identity.

### Trust S3 metadata or persisted size without reading the object

Rejected. The GI-1 gate recalculates the digest over actual bytes and enforces limits while reading.

### Authorize by evidence ID alone

Rejected. The exact initiative subject, authenticated actor/admin assertion, version and digest are
part of the authorization context.

### Add an evidence-to-model endpoint now

Rejected. Connecting content to a model requires a separate purpose, egress, minimization,
retention, audit and authority review.

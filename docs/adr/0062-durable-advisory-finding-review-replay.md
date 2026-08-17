# ADR 0062 - Durable advisory finding review replay

- **Status:** Accepted
- **Date:** 2026-08-17
- **Decision owners:** Engineering, architecture, security and AI Governance

## Context

ADR 0060 introduced a content-minimized audit receipt for an authorized, non-authoritative review.
Its generated `review_id` identified evidence after execution but did not give a caller stable
request identity. ADR 0061 then selected initiative owner or administrator authorization without
exposing a delivery path.

Repeated attempts could therefore create multiple receipts, and concurrent attempts had no defined
winner or replay behavior. Correlation identity cannot safely fill that role because one trace can
contain multiple commands. Before any delivery boundary is introduced, the application needs
durable request semantics that survive process restarts and races without retaining untrusted
finding content or weakening current authorization.

## Decision

GI-3B requires a caller-supplied, non-nil UUID `request_id` distinct from `correlation_id` and the
generated `review_id`. The request identity binds the complete content-free review command:

- finding schema, ID, type, agent-run ID and canonical-envelope SHA-256;
- governed subject and correlation identities;
- disposition, reviewer identity and administrator-access fact.

Every attempt revalidates the closed finding envelope and performs current subject authorization
before reading durable receipt state. Authorization is therefore not cached by a successful prior
attempt.

The first successful attempt creates an immutable review receipt with schema version `1.0`, UTC
time, generated `review_id` and a SHA-256 digest over every bound command field plus receipt
identity, schema, time and version. One SQLAlchemy unit of work inserts the minimized receipt and
appends its hash-chained audit event in the same transaction. A unique database constraint on
`request_id` makes the database the concurrency arbiter.

An exact replay verifies the stored receipt structure and digest, compares the complete binding,
and returns the original receipt without adding another row or audit event. Reuse with a different
finding, digest, actor, subject, correlation, disposition or administrator-access fact returns the
same content-free `conflict`. Invalid stored evidence also fails as `conflict`.

When concurrent inserts collide, the loser rolls back its failed transaction, reloads the unique
winner once and applies the same integrity and exact-binding checks. A missing or divergent winner
fails closed instead of retrying indefinitely or overwriting evidence.

`governance_finding_review_receipts` is append-only application evidence. It stores only receipt,
request, finding and run identities; schema versions; finding type; candidate and receipt digests;
subject, correlation and reviewer identities; disposition; administrator-access fact; UTC time and
version. It stores no statement, confidence, source reference, prompt, provider/model identity,
source content, tool output or free-form rationale.

This decision adds no endpoint, listing, task, queue, provider, model execution, finding-content
retention, review supersession or governed-state transition. The Governance Finding `1.0` wire
contract remains unchanged.

## Alternatives considered

### Use correlation identity as the idempotency key

Rejected. Correlation groups related work and is not a unique command identity. Reusing it would
collapse legitimate reviews within one trace.

### Treat the audit table as replay state

Rejected. Audit events are optimized for integrity evidence, not a typed, uniquely constrained
application lookup. Querying payload JSON would weaken validation and concurrency semantics.

### Keep deterministic replay only in process memory

Rejected. Memory cannot survive restarts, multiple workers or database-visible races.

### Persist the complete finding with the receipt

Rejected. Replay needs a canonical digest and identities, not duplicated untrusted content. Full
retention would prematurely decide privacy, deletion, access and safe-rendering policy.

### Upsert or use last-write-wins on request reuse

Rejected. Mutation would erase evidence of the first accepted command and let divergent retries
rebind an idempotency identity.

## Consequences

- exact retries return byte-equivalent receipt facts across workers and restarts;
- concurrent duplicates converge on one receipt and one audit event;
- current authorization is checked even when a receipt already exists;
- `request_id` identifies a command while `review_id` identifies its immutable evidence;
- divergent reuse and corrupted stored evidence share a bounded content-free conflict;
- one additional indexed table and lookup are required for review execution;
- replay cannot reconstruct or display the finding from minimized evidence.

## Security and privacy impact

The durable row excludes finding statements and source/model content. Its candidate digest binds
the complete envelope, while the receipt digest detects changed metadata before replay. Database
constraints close schema, type, disposition, digest length and version values. Authorization runs
before lookup so request identities do not become bearer capabilities after ownership or role
changes.

Public failures expose no stored value, finding content or database detail. Operators must still
treat actor, subject and correlation identifiers as controlled metadata and avoid logging submitted
finding payloads. Digests prove binding and integrity, not truth, provenance authenticity or
compliance.

## Operational impact

Migration `0021` creates the receipt table, one unique request constraint and bounded lookup
indexes. New reviews add one receipt lookup and, on first execution, one receipt insert plus the
existing audit append in a single transaction. Exact replay adds no new audit evidence. A database
unique conflict triggers one rollback and one winner reload; there is no unbounded retry loop.

Backups, restores and retention policy must include the minimized receipt table together with the
audit chain. Monitoring should distinguish content-free `conflict` from dependency failure without
recording findings. Deployment still registers no consumer or externally callable route.

## Follow-up

- define review listing, supersession and response contracts before delivery exposure;
- define retention, legal hold, deletion, export and access rules if finding content is ever stored;
- derive `request_id`, actor and administrator facts from a trusted delivery boundary with abuse
  controls;
- evaluate authorization-to-persistence race requirements if external exposure needs a stronger
  ownership snapshot;
- route accepted recommendations only through existing authoritative use cases and their separate
  validation, authorization, segregation-of-duties and audit controls.

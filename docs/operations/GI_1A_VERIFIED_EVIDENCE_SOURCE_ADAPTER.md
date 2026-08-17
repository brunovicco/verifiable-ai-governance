# GI-1A verified evidence source adapter

- **Status:** Current
- **Owner:** Platform engineering, security and AI Governance
- **Last reviewed:** 2026-08-17
- **Review trigger:** Evidence eligibility, authorization, storage or knowledge-consumer change
- **Authoritative sources:** ADR 0058, ADR 0057 and the verified-evidence adapter tests

GI-1A connects the deterministic Governance Knowledge gate to clean, trusted evidence uploads in
private object storage. It does not expose a content endpoint or connect evidence to a model,
retrieval engine or external provider.

## Canonical reference

For an eligible `EvidenceRecord`:

```json
{
  "artifact_id": "evidence:11111111-1111-4111-8111-111111111111",
  "version": "1",
  "node_id": null,
  "section": null,
  "content_digest": "<persisted lowercase SHA-256>"
}
```

The public reference never contains filename, bucket, object key or S3 URI.

## Eligibility and authorization

The metadata reader returns only clean, trusted uploads with private storage metadata. The adapter
then requires:

- a canonical non-nil evidence UUID;
- no node or section selector;
- exact evidence version and digest;
- the canonical `evidence/{initiative_id}/{evidence_id}` storage key;
- `subject_id` equal to the evidence initiative;
- `actor_id` equal to the initiative owner, unless the authenticated principal is an administrator.

Denied requests do not open object storage. Resolution also fails unless authorization succeeded on
the same request-scoped adapter instance with the same actor, subject, correlation ID, admin
assertion and exact reference.

## Configuration

| Environment variable | Default | Purpose |
|---|---:|---|
| `GOVERNANCE_KNOWLEDGE_MAX_SOURCES` | `10` | Maximum references in one gate invocation |
| `GOVERNANCE_KNOWLEDGE_MAX_SOURCE_BYTES` | `10485760` | Maximum actual bytes for one source |
| `GOVERNANCE_KNOWLEDGE_MAX_TOTAL_BYTES` | `20971520` | Maximum actual bytes across unique sources |

The aggregate limit must be greater than or equal to the per-source limit. Existing object-storage
connect/read timeout, retry, TLS and encryption settings also apply.

## Verify locally

Run the adapter, foundation and architecture tests:

```bash
uv run pytest -q \
  apps/api/tests/test_governance_knowledge_evidence_adapter.py \
  apps/api/tests/test_governance_knowledge_application.py \
  apps/api/tests/test_architecture.py
```

Run the complete repository gate before merging:

```bash
uv run python scripts/quality_gate.py
```

## Failure triage

| Failure | Check |
|---|---|
| `source_unavailable` before S3 | canonical UUID/reference, initiative ownership, subject binding, clean/trusted upload, version/digest and storage key |
| `dependency_unavailable` during authorization | database availability and evidence metadata integrity |
| `dependency_unavailable` during resolution/read/close | configured bucket, object existence, S3 network/TLS credentials and timeout |
| `integrity_mismatch` | object bytes differ from the persisted upload digest; preserve the object and investigate |
| `limit_exceeded` | source count and actual per-source/aggregate byte limits |

Failures and logs must not include document bytes, filename, bucket, key or URI. Do not repair an
integrity mismatch by updating the persisted digest; treat replacement content as a new evidence
artifact.

## Security and operational boundary

- bucket substitution is rejected before the S3 request;
- storage keys must match the application-generated evidence path exactly;
- external URI evidence is never resolved by this adapter;
- S3 response metadata does not replace application SHA-256 verification;
- stream cleanup runs after success and failure;
- current code has no HTTP or model consumer, so no content is exposed by a production request path.

Before adding a consumer, define and test content-access audit events, cancellation behavior,
purpose limitation, data classification, model/provider egress, retention and reviewer access. A
matching digest proves byte integrity, not evidence truth, control effectiveness or compliance.

# ADR 0006 - Secure evidence upload

- Status: accepted
- Date: 2026-07-31

## Context

A reference typed into an approval does not prove that an artifact was received,
preserved, or verified. The portal needs to accept files from non-technical areas
without turning the API, the database, or the logs into repositories of potentially
malicious and sensitive content.

## Decision

- keep existing approval references as `trusted_source=false` and distinguish them
  from verified uploads;
- restrict upload to the initiative owner or a governance administrator;
- initially accept PDF, PNG, JPEG, TXT, CSV, and JSON, with extension, media type,
  signature, and textual structure validated on the server;
- bound the stream during reading and compute SHA-256 over the same bytes sent to the
  scanner and to storage;
- limit the ASGI body before the multipart parser and temporary spooling, including
  when `Content-Length` is absent;
- require a clean ClamAV verdict via `INSTREAM`; unavailability, timeout, error, or an
  ambiguous response blocks the operation;
- use a random key `evidence/{initiative_id}/{evidence_id}`, never the name provided
  by the client;
- write the file to a private S3 bucket, with auto-create allowed only in the local
  environment and server-side encryption mandatory outside local/test;
- persist metadata and the audit event in the same transaction; if it fails after the
  upload, roll back and compensate by deleting the object;
- do not return the bucket, key, or internal URI in the API and do not log the name or
  content in the audit log;
- restrict upload and metadata query to the owner or administrator;
- configure size, allowlist, endpoints, timeouts, bucket, region, and credentials via
  environment variables.

The use case defines ports for stream, scanner, object storage, persistence, audit,
and transaction. FastAPI, SQLAlchemy, ClamAV, and S3 remain external adapters,
preserving Dependency Inversion and testability.

## Consequences

- the flow fails closed if the scanner or object storage is unavailable;
- structural validation reads at most the configured limit in memory after spooling;
  the default is 10 MiB and the configuration ceiling is 50 MiB;
- ClamAV detects known malware, but does not replace content disarm and
  reconstruction nor human review; PDFs are not rendered by the portal;
- signature updates, retention, bucket versioning/immutability, and lifecycle remain
  operational responsibilities;
- the bucket must be private, use a least-privilege credential, and a retention
  policy; ClamAV must remain on a private network and the runtime's temporary
  directory must use protected ephemeral storage;
- a failed compensating delete can leave an orphaned object; bucket lifecycle and
  reconciliation must remove it without relying on public listing;
- download and granular authorization for reviewers are not part of this slice and
  must use short-lived signed URLs, never making the bucket public.
- development images use verified version tags; hardened deployments must also pin
  their digests and verify SBOM/signature in the supply-chain pipeline.

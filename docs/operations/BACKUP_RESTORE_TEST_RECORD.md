# Backup and restore test record

## Run 2026-08-01

| Field | Result |
|---|---|
| Environment | Local Compose on ARM64 host |
| PostgreSQL | 17.10 |
| MinIO | RELEASE.2025-04-22T22-12-26Z |
| Captured revision | `0004` |
| Public tables | 12 |
| S3 upload metadata | 0 |
| Source S3 objects | 0; bucket not yet materialized |
| Directory permission | `0700` |
| File permission | `0600` |
| Create | passed |
| Hash and catalog verify | passed |
| Isolated restore | passed |
| Temporary database cleanup | passed; 0 `governance_restore_%` databases remaining |
| Source preservation | revision `0004`, 1 initiative, 9 gates and 1 evidence item preserved |

The real test used a 33,245-byte dump and restored the revision and all 12 tables
into a new database. It also created and removed an isolated S3 bucket. The source
had no uploads stored in S3; export, upload, SHA-256 re-read and non-empty content
removal are covered by the adapter's deterministic test.

This record proves the flow ran in the reference environment, but it does not define
RPO, RTO or production compliance. The first enterprise deployment must run a new
restore test with representative non-production evidence, encryption and managed
services chosen by the organization.

# Backup and restore runbook

## Purpose and scope

This runbook protects the two backing services that make up the verifiable registry:

- PostgreSQL, which holds initiatives, decisions, assessments, metadata and audit;
- S3 object storage, which holds the private evidence files referenced by the
  database.

The repository's utility is an executable reference for a local or controlled
environment. Production should use the equivalent managed capabilities, such as PITR,
encrypted snapshots, object versioning and replication, preserving the same
manifest, assurance and access criteria.

## Package guarantees

Each package is created in a private temporary directory and published via atomic
rename only after completion. It contains:

```text
backup/
├── manifest.json
├── manifest.sha256
├── postgres.dump
└── evidence/
    └── files identified by index and key hash
```

The manifest records the format version, a timestamp with timezone, logical origin,
Alembic revision, table count and, for each artifact, path, size and SHA-256. Object
keys stay in the manifest but do not appear in operational output. Hashes detect
corruption; they do not replace signing, access control or immutable storage against
an attacker capable of replacing both package and manifest.

The bucket's object count is compared against trusted upload metadata in the
database. A bucket not yet materialized only represents an empty inventory when the
database also references no objects; divergences stop the capture in a fail-closed
manner.

Existing directories, existing databases and existing buckets are never overwritten.
Restore accepts only plain database names and a valid S3 bucket, always distinct from
the configured sources.

## Prerequisites

- healthy `postgres` and `object-storage` Compose services;
- `uv` and dependencies synced;
- enough free space for the dump and all objects;
- exclusive access and an encrypted destination for the package;
- a maintenance window or other mechanism preventing new uploads and changes.

The utility reads configuration from the environment per Twelve-Factor. The defaults
match the local Compose setup. In another configuration, provide `POSTGRES_DB`,
`POSTGRES_USER`, `BACKUP_OBJECT_STORAGE_ENDPOINT_URL`, `OBJECT_STORAGE_REGION`,
`OBJECT_STORAGE_BUCKET` and short-lived credentials via a secure mechanism. The
variables `BACKUP_OBJECT_STORAGE_ACCESS_KEY`, `BACKUP_OBJECT_STORAGE_SECRET_KEY` and
`BACKUP_OBJECT_STORAGE_SESSION_TOKEN` take precedence and allow a least-privilege
identity separate from the application; when absent, the adapter accepts the SDK's
default credential chain.
Timeouts and retries are also explicit configuration via
`BACKUP_DATABASE_COMMAND_TIMEOUT_SECONDS`, `BACKUP_S3_CONNECT_TIMEOUT_SECONDS`,
`BACKUP_S3_READ_TIMEOUT_SECONDS` and `BACKUP_S3_MAX_ATTEMPTS`.

## Create and verify

Choose a new directory; the command fails if it already exists.

```bash
docker compose stop web api
make backup BACKUP_DIR=backups/2026-08-01
make backup-verify BACKUP_DIR=backups/2026-08-01
make backup-restore-test BACKUP_DIR=backups/2026-08-01
docker compose start api web
```

`backup-verify` recomputes all hashes and asks `pg_restore` to read the catalog.
`backup-restore-test` creates random destinations, restores all content, compares
database state, re-reads objects to validate SHA-256, and removes the isolated
destinations. A test that fails to complete cleanup returns failure and requires
operational intervention.

After success:

1. record the identifier, time, environment, Alembic revision, counts and outcome;
2. encrypt the package with a key managed outside the backup itself;
3. move a copy to a location with an independent failure domain and access;
4. apply retention and disposal approved by Privacy, Security and Records Management;
5. monitor the age of the last valid backup and the last tested restore.

## Controlled restore

The command restores only to destinations that do not yet exist. This allows
validating and promoting via cutover, without destroying the source:

```bash
make backup-restore \
  BACKUP_DIR=backups/2026-08-01 \
  RESTORE_DATABASE=ai_governance_recovered \
  RESTORE_BUCKET=governance-evidence-recovered
```

Before cutover:

1. confirm the JSON result and run smoke tests with isolated configuration;
2. check the Alembic revision, counts, an authorized evidence sample and the audit
   chain;
3. record approval from Operations, the system owner and Security/Privacy when
   applicable;
4. switch endpoints via deploy configuration, without renaming or deleting the
   source;
5. keep rollback available until acceptance and only then apply the disposal policy.

Restore does not run additional migrations. The package must be restored in the
state it was captured; any upgrade happens afterward, through the project's existing
explicit, blocking process.

## Minimum organizational policy

RPO, RTO, frequency and retention must be approved based on risk and legal
obligation; the framework does not invent a universal value. The organization's
policy needs to define:

- measurable objectives per tier and a responsible owner;
- automatic backups, alerts and periodic restore testing;
- encryption in transit and at rest, segregation of duties and least privilege;
- immutability or protection against malicious deletion and ransomware;
- location of backups, subprocessors and international transfer assessment;
- retention consistent across database, evidence, audit and data subject requests;
- incident procedure, communication and operational evidence collection.

Never include credentials, encryption keys or logs with evidence content in the same
package. Do not publish backups to Git, public CI artifacts, or buckets without an
explicit private policy.

## Failures and operational recovery

- Create failure: the temporary directory is not published and is removed.
- Mismatched hash or unreadable catalog: quarantine the package and use another
  copy; do not force the restore.
- Destination already exists: choose a new destination and investigate the source
  of the conflict.
- Partial restore: the use case removes destinations created by that attempt.
- Restore-test cleanup failed: treat it as an operational incident and remove only
  the exact destinations reported in the result/error, after independent
  confirmation.
- Source unavailable: preserve minimized technical logs and engage the backing
  service owner; do not degrade to a partial backup.

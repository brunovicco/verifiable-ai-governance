# Threat model

- **Status:** Draft for recurring review
- **Owner:** Security architecture
- **Last reviewed:** 2026-08-03
- **Review trigger:** New external dependency, trust boundary, sensitive data path or privileged action

## Scope

This threat model covers the portal, API, policy engine, PostgreSQL, private object
storage, malware scanner, OIDC provider, Microsoft Graph OBO integration, external model
router, audit trail and operational interfaces.

It does not model the internal security of an AI provider, identity provider or cloud
platform beyond the interfaces used by this application.

## Protected assets

- identities and governance capabilities;
- initiative and assessment facts;
- approval decisions and review snapshots;
- model and agent approved scope;
- evidence content and metadata;
- policy and authorization catalogs;
- audit sequence and integrity material;
- incident, exception and remediation state;
- database and object-storage backups;
- secrets and service credentials.

## Adversaries and failure actors

- unauthenticated external attacker;
- authenticated user exceeding assigned authority;
- owner attempting self-approval;
- reviewer acting outside the reviewer's area;
- compromised browser or session;
- malicious file uploader;
- compromised external router or directory dependency;
- privileged infrastructure operator;
- supply-chain attacker;
- accidental operator or deployment error;
- stale or inconsistent distributed process.

## Trust boundaries

See [Trust boundaries](../architecture/TRUST_BOUNDARIES.md) for the system diagram.

Key boundary crossings:

1. browser to API;
2. API to identity provider and Microsoft Graph;
3. API to PostgreSQL;
4. API to ClamAV and object storage;
5. API to external model router;
6. operational export or backup to external storage;
7. future runtime telemetry into the governance platform.

## Threat register

| ID | Threat | Example | Primary mitigations | Residual concern |
|---|---|---|---|---|
| TM-01 | Identity spoofing | Forged bearer token or development headers in shared environment | Cryptographic OIDC validation; local/shared mode separation; issuer and audience checks | Misconfiguration of environment or identity provider |
| TM-02 | Privilege escalation | Group name or department grants approval rights | Explicit App Role/object-ID catalog; unknown mappings deny; provenance recorded | Incorrect catalog administration |
| TM-03 | Self-approval | Owner attempts to approve an initiative, model or agent | Domain-level segregation-of-duties checks | Collusion between separate identities |
| TM-04 | Stale authorization | Removed directory role remains usable | Short TTL, catalog-digest binding, distributed invalidation and emergency block | Delay until provider/session revocation completes |
| TM-05 | Replay or stale write | Client overwrites newer decision state | Expected version and optimistic concurrency | Business-level duplicate requests without idempotency key |
| TM-06 | Review-history rewriting | User edits prior answers or approvals after change request | Immutable rounds and snapshots; explicit resubmission | Privileged database compromise |
| TM-07 | Policy tampering | Control or authorization catalog silently changes | Version, digest, schema validation, duplicate-ID rejection and fail-closed startup | Authorized but malicious repository/deployment change |
| TM-08 | Evidence malware | Uploaded executable or malformed document attacks reviewer | Allowlist, signature validation, hard size limit, ClamAV and private storage | Zero-day or active content accepted by allowed format |
| TM-09 | Evidence substitution | Stored object differs from reviewed object | SHA-256 metadata and generated storage key | Hash metadata and object changed by fully privileged attacker |
| TM-10 | Sensitive-data leakage | Prompt, assessment answer or evidence appears in logs | Data minimization and structured logging rules | Developer-added logging regression |
| TM-11 | Router authority expansion | External router selects an unapproved model group | Validate response against eligible approved groups; router receives no prompt/document | Compromised runtime bypassing this integration entirely |
| TM-12 | Time-of-check/time-of-use change | Registry scope changes during router call | Pre-call digest, persisted pending decision and fresh post-call revalidation | Changes after final decision but before downstream invocation |
| TM-13 | Dependency fail-open | Graph, ClamAV, database or router outage grants access/action | Explicit fail-closed behavior and safe error categories | Availability impact and operational pressure to bypass controls |
| TM-14 | Audit deletion or rewriting | Privileged actor removes an event | Hash-chained append-only event model and verification | No external WORM or trusted timestamp by default |
| TM-15 | Backup disclosure | Governance database and evidence archive copied | Restricted local permissions, encryption and controlled external storage required | Human handling and retention mistakes |
| TM-16 | Cross-tenant access | Identity from another tenant reaches governed data | Tenant allowlist and stable `(tid, oid)` identity | Misconfigured tenant catalog or future multi-tenancy design |
| TM-17 | Supply-chain compromise | Malicious dependency, action or container image | Locked dependencies, CI, pinned images where appropriate and review | No complete provenance/SBOM enforcement yet |
| TM-18 | Denial of service | Oversized token, upload or expensive request | Size limits, timeouts, pagination validation and rate-limit integration points | Distributed traffic flood without edge controls |
| TM-19 | Exception abuse | Temporary exception becomes permanent bypass | Expiry, compensating controls, independent approval and dashboard visibility | Weak organizational follow-up |
| TM-20 | Kill-switch misuse | Privileged user blocks or restores identity improperly | Restricted endpoint, audit, reason and authorization checks | Insider with legitimate emergency authority |

## AI- and agent-specific threats

The following classes should be reviewed when runtime telemetry and execution adapters
are added:

- prompt injection and indirect prompt injection;
- excessive agency and missing human approval;
- insecure tool or MCP permissions;
- tool-argument manipulation;
- uncontrolled delegation or agent loops;
- model or tool substitution;
- sensitive information disclosure;
- poisoning of retrieval or evaluation evidence;
- unsafe output handling;
- cost and resource exhaustion.

The current platform governs approved scope and routing metadata but does not claim to
inspect every prompt or execute every agent action.

## Abuse cases for security tests

At minimum, automated or reproducible tests should cover:

1. forged, expired, wrong-audience and symmetric-algorithm tokens;
2. guest or unknown role attempting approval;
3. owner attempting self-approval;
4. stale expected version;
5. malformed or oversized evidence;
6. unavailable ClamAV;
7. duplicate control IDs or invalid catalog schema;
8. external router returning an unapproved group;
9. registry scope changing during router decision;
10. emergency blocked identity calling a protected endpoint;
11. restore into an existing database or bucket;
12. audit-chain modification detection.

## Review checklist

- Have new assets or sensitive data been introduced?
- Has a trust boundary changed?
- Is there a new privileged action?
- Can an external dependency expand authority?
- Are time-of-check/time-of-use races possible?
- Does failure deny safely?
- Are logs and telemetry minimized?
- Are incident detection and recovery defined?
- Is there an automated negative test?

# Security model

- **Status:** Current
- **Owner:** Security architecture
- **Last reviewed:** 2026-08-03
- **Review trigger:** Authentication, authorization, evidence, routing or deployment change

## Security objectives

The platform is designed to preserve:

1. **authenticity** of the acting identity;
2. **least privilege** for governance capabilities;
3. **segregation of duties** for material decisions;
4. **integrity** of policy, scope, evidence metadata and audit history;
5. **confidentiality** of sensitive assessments and evidence;
6. **availability with safe failure**, preferring denial over implicit authorization;
7. **traceability** across intake, approval, assets, runtime decisions and incidents.

## Security boundaries

The API is the security authority. The portal is a user interface and must not be relied
on to enforce authorization, state transitions or version checks.

The domain and application layers decide:

- who may mutate an initiative or asset;
- which reviewer area may decide a gate;
- whether the reviewer is independent from the owner;
- whether the expected version matches;
- whether required assessments and approvals are current;
- whether a runtime request remains inside approved scope.

Infrastructure adapters perform cryptographic verification, persistence, network calls,
malware scanning and object storage, but do not own governance policy.

## Identity and authentication

### Local mode

Local development uses explicit demonstration identity headers. This mode must remain
separated from shared or production-like environments.

### Generic OIDC

Outside local mode, authentication requires OIDC with:

- HTTPS issuer and JWKS endpoints;
- asymmetric signing algorithms;
- signature verification;
- issuer and audience validation;
- required subject, issue-time and expiry claims;
- bounded token size and network timeouts.

Unknown claims or roles do not become authorization.

### Microsoft Entra mode

The stable identity is the tenant/object pair `(tid, oid)`. The tenant must be explicitly
allowed. Guest or ambiguous account classification loses approval and administrative
capabilities by default.

Authorization may be derived only from configured App Roles or directory object IDs in
a versioned tenant-specific catalog. Department and group display names do not grant
access.

Microsoft Graph OBO is used for minimal profile and transitive-group resolution. The
application does not expose group object IDs or their count to the frontend.

## Authorization

Authorization is capability-oriented and area-specific. Platform administration does
not automatically confer authority to approve architecture, security, privacy or other
governance gates.

Material rules include:

- the owner cannot approve the owner's own initiative or governed asset;
- a model review belongs to Architecture;
- an agent review belongs to Security;
- high-risk decisions can require multiple independent areas;
- temporary exceptions cannot be approved by the same role that requests or implements them;
- every decision records identity and authorization provenance.

## Authorization cache

Derived directory authorization may be cached in PostgreSQL for a short bounded period.
A reusable snapshot must remain:

- unexpired;
- linked to the current authorization-catalog digest;
- free from a later invalidation event;
- bound to the stable identity.

The cache must not persist bearer tokens, profile fields or group object IDs.

## Emergency access restriction

A separate platform-level restriction is checked after authentication and before every
protected route. Failure to read this control blocks the request. Blocking or restoring
an identity also invalidates derived authorization and creates an audit event.

This control supplements but does not replace provider-side account disablement, role
removal or session revocation.

## Evidence security

Uploaded evidence follows a fail-closed pipeline:

1. stream with a hard size limit;
2. validate allowed media type and file signature;
3. calculate SHA-256;
4. scan with ClamAV;
5. write to private object storage using an application-generated key;
6. persist metadata and audit in a transaction;
7. delete the object as compensation if the transaction fails.

The API does not expose internal bucket names or object keys. Original file names are
presentation metadata only.

Outside local mode, object storage should use controlled bucket creation, server-side
encryption, restricted credentials, defined retention and monitored access.

## Audit integrity

Audit events are append-only and hash-chained with a configured salt. The chain makes
later modification or removal detectable when verification is performed.

It does not by itself provide:

- WORM guarantees;
- external timestamping;
- digital signatures;
- cryptographic non-repudiation;
- protection from a fully compromised application and database administrator.

Production assurance may add external append-only storage, SIEM forwarding, signed
checkpoints or trusted timestamping.

## Runtime routing security

The platform validates governance scope before calling an external model router. Only
minimized operational metadata is sent; prompts and documents are excluded.

A router response is accepted only when:

- the system is operational;
- the agent is approved with a current review;
- at least one approved model remains eligible;
- data class and cost limits are satisfied;
- the returned logical group maps to an eligible model;
- a fresh read confirms the approved scope did not change during the call.

Dependency failure, malformed responses or scope mismatch fail closed.

## Secrets and configuration

Secrets must not be committed. Production secrets should be supplied by a secret manager
or workload identity and rotated through a documented procedure.

Configuration is validated before serving traffic. Security-relevant defaults that are
acceptable for local use must be rejected outside local mode.

## Logging and privacy

Logs and telemetry should prefer identifiers, digests, categories, timing and outcomes.
They should not contain prompts, evidence content, credentials, tokens, full assessment
answers or model responses by default.

## Residual risks

Important residual risks include:

- a privileged operator changing application code and database state together;
- incorrect organizational authorization mappings;
- malicious but structurally valid evidence;
- vulnerable third-party dependencies or container images;
- incomplete real-tenant identity validation;
- delayed external identity revocation;
- misuse of approved scope by a compromised runtime not integrated with enforcement;
- absence of external immutable audit storage.

See [Threat model](THREAT_MODEL.md) and
[Production readiness](../operations/PRODUCTION_READINESS.md).

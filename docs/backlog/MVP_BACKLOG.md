# MVP backlog

## P0 - Make the core usable

- [x] Monorepo, local setup, PostgreSQL, API, portal, tests and CI.
- [x] Registration, triage, conditional gates, SoD, auditing and versioning.
- [x] CRUD and screens for AI systems, models and agents linked to the approved
  initiative.
- [x] Structured assessment for AIA, RIPD and international processing.
- [x] Initial catalog of 25 controls in YAML and applicability view.
- [x] Secure evidence upload with object storage, file checksum and malware scan.
- [x] Review workflow, change request and resubmission without erasing history.
- [x] OIDC integration validated with at least one provider and group mapping.
- [x] Explicit, blocking migrations at Compose startup.
- [x] Backup/restore policy tested for PostgreSQL and evidence.
- [x] Make the local environment's ClamAV image compatible with ARM64 hosts.

## P1 - Operation and assurance

- [x] Portal adapter via Microsoft Entra ID, authorization code with PKCE and
  session cache.
- [ ] Login validation against a real Entra tenant and Conditional Access.
- [x] Corporate identity via `(tid, oid)`, tenant allowlist and guest policy.
- [x] Microsoft Graph via OBO for profile, `department` and the user's transitive
  groups.
- [x] Versioned catalog of Entra App Roles/object IDs for approval areas.
- [ ] Group overage, pagination, throttling, cache, revocation and stale identity
  fail-closed.
  - [x] Reliable pagination, bounded retry, jitter and content-free throttling
    events.
  - [x] Explicit group overage without following token-controlled URLs.
  - [x] PostgreSQL cache with TTL, freshness, catalog binding and distributed
    invalidation.
  - [x] Persistent platform emergency block/restore, fail-closed and audited.
  - [ ] Provider-side session revocation and validation against a real Entra
    tenant.
- [x] Model/agent registry with approved scope, region, version and review dates.
- [x] `policy-model-router` decision adapter.
- [ ] Sanitized telemetry ingestion from `a2a-otel-kit`.
- [ ] Evidence contracts inspired by `engineering-loop-schemas`.
- [ ] Isolated execution record from `alicerce`.
- [ ] Import of evaluations and regressions from `ragforge`.
- [x] Dashboard of violations, blocked actions, drift (unavailable), cost
  (limits) and overdue reviews.
- [x] Incidents, kill switch, temporary exceptions and remediation plan.

## P2 - Scale and portfolio

- [ ] Overlays for financial services, HR, healthcare and corporate knowledge.
- [x] Supporting crosswalk with NIST AI RMF, NIST AI 600-1, OWASP LLM Top 10,
  OWASP Agentic Top 10 and MITRE ATLAS, with citations read directly from the
  official source texts (ISO/IEC 42001 pending - a licensed standard, no source
  text).
- [ ] Evidence package export for audit.
- [ ] APIs/webhooks for CMDB, data catalog, CI/CD and GRC.
- [x] Executive metrics for coverage, cycle time (no declared target), residual
  risk and control effectiveness (unavailable).

## Definition of done

A story is not done just because it has a screen or endpoint. It requires a
contract, authorization, persistence/versioning where applicable, an audit event,
tests, documentation, understandable messages and safe behavior when dependencies
fail.

# Capability matrix

- **Status:** Current
- **Owner:** Product and architecture
- **Last reviewed:** 2026-08-03
- **Review trigger:** Feature merge, deprecation or scope change

## Status definitions

| Status | Meaning |
|---|---|
| Implemented | Functional code path exists and is represented in the current product |
| Partial | Core implementation exists but environment validation or a supporting capability is incomplete |
| Planned | Explicit roadmap or backlog item without a complete current implementation |
| Not intended | Deliberately outside the product claim |

## Product capabilities

| Domain | Capability | Status | Evidence or limitation |
|---|---|---|---|
| Intake | Business-facing initiative registration | Implemented | Portal and API maintain owner and business context |
| Risk | Deterministic preliminary classification | Implemented | Versioned policy returns score, tier, documents and gates |
| Controls | Declarative baseline control catalog | Implemented | 25 YAML controls with explainable applicability |
| Assessments | AI impact assessment | Implemented | Structured, versioned draft and submission lifecycle |
| Assessments | Privacy impact / RIPD | Implemented | Structured and risk-aware workflow |
| Assessments | International processing | Implemented | Captures countries, mechanisms and approval context |
| Reviews | Conditional multidisciplinary gates | Implemented | Business, architecture, security, privacy and other areas as applicable |
| Reviews | Segregation of duties | Implemented | Owner cannot approve own governed scope |
| Reviews | Immutable review rounds | Implemented | Change requests preserve prior snapshots and decisions |
| Evidence | Verified file upload | Implemented | Size/type/signature validation, SHA-256, ClamAV and private storage |
| Evidence | External URI reference | Implemented | Kept distinct from verified uploaded evidence |
| Evidence | Exportable audit package | Planned | Portfolio export remains roadmap work |
| Inventory | AI systems | Implemented | Created from approved initiatives with owner and lifecycle |
| Inventory | Model assets | Implemented | Version, region, routing group and approved scope |
| Inventory | Agent assets | Implemented | Autonomy, tools, model allowlist and operational limits |
| Assurance | Independent model review | Implemented | Architecture-owned decision with validity and scope digest |
| Assurance | Independent agent review | Implemented | Security-owned decision with dependent model validation |
| Runtime | Approved-scope model routing | Implemented | Router result is constrained to currently eligible approved groups |
| Runtime | Runtime telemetry ingestion | Planned | Sanitized adapter integration remains future work |
| Runtime | Drift calculation | Planned | Dashboard exposes unavailability instead of estimating it |
| Runtime | Control effectiveness | Planned | Dashboard exposes unavailability until evidence sources exist |
| Identity | Local explicit demonstration identity | Implemented | Intentionally separated from corporate mode |
| Identity | Generic OIDC validation | Implemented | Asymmetric signature, issuer, audience and required claims |
| Identity | Microsoft Entra portal login | Partial | Adapter and PKCE flow exist; real-tenant validation pending |
| Identity | Microsoft Graph OBO enrichment | Partial | Profile/group resolution implemented; organizational validation pending |
| Identity | Explicit authorization catalog | Implemented | App roles and object IDs map to governance areas with provenance |
| Identity | Emergency platform access restriction | Implemented | Persistent, audited and fail-closed at protected routes |
| Identity | Provider session revocation | Planned | Must be performed through the identity provider |
| Operations | Incident management | Implemented | Detection, severity, remediation and lifecycle |
| Operations | Kill switch | Implemented | Immediate platform containment path |
| Operations | Temporary policy exceptions | Implemented | Expiry and compensating controls required |
| Operations | Executive dashboard | Implemented | Portfolio-level governance and operational metrics |
| Resilience | Explicit schema migration | Implemented | One-shot migration blocks API startup on failure |
| Resilience | Backup and restore verification | Implemented | Manifest, checksums and isolated restore test |
| Integration | CMDB and enterprise GRC | Planned | API/webhook integration roadmap |
| Integration | Data catalog and CI/CD | Planned | API/webhook integration roadmap |
| Sector | Financial-services overlay | Planned | Baseline remains sector-neutral |
| Sector | Health, HR and other overlays | Planned | Additional policy/control layers required |

## Non-claims

The platform does not claim to provide:

- automated legal advice;
- automatic certification against ISO/IEC 42001 or another standard;
- automatic regulatory classification without organizational review;
- a general-purpose model or agent execution platform;
- guaranteed production readiness for every deployment environment;
- cryptographic non-repudiation or WORM storage solely from its hash chain.

## Maintenance rule

A capability must not be changed to “Implemented” based only on a UI placeholder, data
model or roadmap entry. The status requires an end-to-end code path, authorization,
persistence where applicable, audit behavior, tests, documentation and defined failure
semantics.

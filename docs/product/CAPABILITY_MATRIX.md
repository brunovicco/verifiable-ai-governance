# Capability matrix

- **Status:** Current
- **Owner:** Product and architecture
- **Last reviewed:** 2026-08-17
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
| Evidence | Portable scoped audit package | Planned | Release evidence is portable; business audit-package export remains roadmap work |
| Inventory | AI systems | Implemented | Created from approved initiatives with owner and lifecycle |
| Inventory | Model assets | Implemented | Version, region, routing group and approved scope |
| Inventory | Agent assets | Implemented | Autonomy, tools, model allowlist and operational limits |
| Assurance | Independent model review | Implemented | Architecture-owned decision with validity and scope digest |
| Assurance | Independent agent review | Implemented | Security-owned decision with dependent model validation |
| Runtime | Signed scope-bound authorization | Implemented | Runtime permission is derived from approved scope and stable request identity |
| Runtime | Approved-scope model routing | Implemented | Router result is constrained to currently eligible approved groups |
| Runtime | Trusted violation evidence | Implemented | Valid fail-closed Router denials persist minimized identity, code and integrity digest |
| Runtime | Sanitized telemetry ingestion | Implemented | Per-agent authenticated ingestion stores bounded metadata without prompt/payload content |
| Runtime | Runtime assurance evaluation | Implemented | Bounded observations feed explicit assurance state rather than inferred dashboard values |
| Runtime | Governed actuation | Implemented | Runtime controls support containment and restoration with correlated audit evidence |
| Runtime | Long-horizon statistical drift analytics | Partial | Operational assurance exists; broad historical/statistical drift analytics remain future work |
| Runtime | Enterprise control-effectiveness analytics | Partial | Runtime observations support bounded assurance; organization-wide effectiveness scoring is not claimed |
| Release | SBOM and vulnerability evidence | Implemented | Versioned release evidence is content-addressed and offline-verifiable |
| Release | Build/source provenance evidence | Implemented | Frozen component commits and build recipe inputs are bound into provenance |
| Release | Runtime benchmark and SLO evidence | Implemented | Release benchmark captures observed latency/availability and explicit SLO verdicts |
| Release | Frozen-source clean-install evidence | Implemented | Tooling executes the exact frozen Governance source through empty-database migration proof |
| Release | Coordinated rc2 evidence index | Implemented | Tooling binds manifest, security, provenance, runtime and clean-install roots; rc2 is generated after source freeze |
| Identity | Local explicit demonstration identity | Implemented | Intentionally separated from corporate mode |
| Identity | Generic OIDC validation | Implemented | Asymmetric signature, issuer, audience and required claims |
| Identity | Microsoft Entra portal login | Partial | Adapter and PKCE flow exist; real-tenant validation pending |
| Identity | Microsoft Graph OBO enrichment | Partial | Profile/group resolution implemented; organizational validation pending |
| Identity | Explicit authorization catalog | Implemented | App roles and object IDs map to governance areas with provenance |
| Identity | Emergency platform access restriction | Implemented | Persistent, audited and fail-closed at protected routes |
| Identity | Provider session revocation | Planned | Must be performed through the identity provider |
| Operations | Incident management | Implemented | Detection, severity, remediation and lifecycle |
| Operations | Kill switch / runtime containment | Implemented | Immediate governed containment path with runtime-control integration |
| Operations | Temporary policy exceptions | Implemented | Expiry and compensating controls required |
| Operations | Executive dashboard | Implemented | Portfolio-level governance and operational metrics |
| Resilience | Explicit schema migration | Implemented | One-shot migration blocks API startup on failure |
| Resilience | Fresh-install migration regression | Implemented | Empty PostgreSQL migration chain is tested independently from normal development volumes |
| Resilience | Backup and restore verification | Implemented | Manifest, checksums and isolated restore test |
| Engineering | Canonical deterministic reference demo | Implemented | Stable semantic identities plus dedicated reference-demo CI |
| Engineering | Public repository hygiene gate | Implemented | Local coding-agent/editor state and generated paths are rejected when tracked |
| Governance Intelligence | Advisory finding trust boundary and contracts | Implemented | Closed shared schemas and a consumer-owned port keep findings untrusted, non-authoritative and free of provider coupling |
| Governance Intelligence | Cross-repository contract compatibility gate | Implemented | Built-wheel inspection and isolated probes protect v1 against current Policy Model Router and Credit Desk checkouts |
| Governance Intelligence | Versioned contract compatibility and evolution | Implemented | Immutable schema snapshots, a closed manifest, fail-closed dispatch and backward-reader rules prevent silent v1 drift |
| Governance Intelligence | Governed knowledge and retrieval foundation | Implemented | Verified-only application ports enforce authorization, exact-version resolution, bounded reads and SHA-256 before adapters; no provider or retrieval adapter is connected |
| Governance Intelligence | Verified uploaded evidence source adapter | Implemented | Canonical evidence identity, initiative owner/admin authorization and exact private S3 reads feed the GI-1 gate; no HTTP, retrieval or model consumer exists |
| Governance Intelligence | Governed advisory analysis orchestration | Implemented | Purpose and source access are audited before analysis; candidate type, citations, provenance, limits and terminal audit are validated before advisory envelopes are released |
| Governance Intelligence | Governed advisory analysis composition policy | Implemented | Settings-backed source, finding and timeout limits plus one request-scoped audit unit compose GI-2 internally without selecting a provider or exposing a consumer path |
| Governance Intelligence | Advisory finding review boundary | Implemented | Revalidated, authorized review produces only closed non-authoritative dispositions and a digest-bound minimized audit receipt; no finding content or governed state is persisted |
| Governance Intelligence | Initiative finding review authorization | Implemented | Canonical initiative owner/admin policy uses a minimal short-lived ownership read; denial is content-free and the internal builder has no delivery exposure |
| Integration | CMDB and enterprise GRC | Planned | API/webhook integration roadmap |
| Integration | Data catalog and CI/CD | Planned | API/webhook integration roadmap |
| Sector | Financial-services overlay | Planned | Baseline remains sector-neutral; canonical credit scenario is a demo, not a policy overlay |
| Sector | Health, HR and other overlays | Planned | Additional policy/control layers required |

## Evidence boundaries

“Implemented” does not mean every external dependency has been validated in every production
environment. In particular:

- the deterministic canonical seed uses a local Router adapter for reproducible fixture creation;
- the separate governed-actuation E2E is the cross-repository proof for live Router/runtime paths;
- Microsoft Entra/Graph code exists but real-tenant and Conditional Access validation remains
  explicitly partial;
- release-candidate tooling is implemented before the final `0.2.0-rc2` evidence is regenerated;
- runtime assurance does not claim long-horizon statistical model-drift science or enterprise-wide
  control-effectiveness scoring.

## Non-claims

The platform does not claim to provide:

- automated legal advice;
- automatic certification against ISO/IEC 42001 or another standard;
- automatic regulatory classification without organizational review;
- a general-purpose model or agent execution platform;
- guaranteed production readiness for every deployment environment;
- cryptographic non-repudiation or WORM storage solely from its hash chain;
- storage of prompts/model responses as a prerequisite for runtime assurance.
- authority for agents, models, retrieval results or external findings to approve, authorize or
  declare compliance.

## Maintenance rule

A capability must not be changed to “Implemented” based only on a UI placeholder, data model,
roadmap entry or deterministic fixture. The status requires an end-to-end code path,
authorization, persistence where applicable, audit behavior, tests, documentation and defined
failure semantics. External integration claims additionally require the corresponding integration
or E2E evidence.

# Product roadmap

- **Status:** Current
- **Owner:** Product and architecture
- **Last reviewed:** 2026-08-17
- **Review trigger:** Quarterly planning or material dependency change

This roadmap communicates product outcomes. Accepted ADRs, the capability matrix and the technical
backlog remain authoritative for implemented behavior and individual work items.

## Now - finish a reviewable v0.2.0 reference release

### Outcome: a reviewer understands the proof in minutes

- keep the English and Brazilian Portuguese READMEs aligned with implemented behavior;
- maintain a five-minute canonical walkthrough for technical and non-technical reviewers;
- preserve real, synthetic-data visual evidence instead of decorative screenshots;
- keep public engineering guidance independent of local coding tools;
- enforce repository hygiene in tests and the quality gate;
- run the deterministic canonical demo in dedicated CI.

### Outcome: the v0.2.0 release is independently verifiable

- freeze the public source tree only after repository hardening;
- regenerate `0.2.0-rc2` manifest, security, provenance, benchmark and clean-install evidence;
- bind those roots into the coordinated release-candidate evidence index;
- verify the evidence offline before relying on GitHub attestations;
- obtain GitHub OIDC/Sigstore attestations for the release subjects;
- perform final release validation before creating the v0.2.0 tag.

### Outcome: runtime governance remains demonstrably connected to execution

Already implemented reference paths must remain regression-protected for:

- signed authorization and approved-scope routing;
- trusted fail-closed runtime violation evidence;
- sanitized runtime telemetry ingestion;
- bounded runtime assurance;
- governed containment/restoration;
- benchmark/SLO release evidence.

New work in this area should improve evidence quality or operational depth rather than re-labeling
existing deterministic fixtures as live integration proof.

## Next - deepen enterprise integration and portable audit outcomes

### Outcome: Governance Intelligence grows from an explicit non-authoritative boundary

- GI-0 establishes closed, versioned advisory finding/source/provenance contracts and a
  consumer-owned application port;
- PH-1 establishes an artifact-first cross-repository compatibility gate against the current
  Policy Model Router and Credit Desk checkouts;
- PH-2 establishes immutable schema snapshots, fail-closed version dispatch and explicit
  backward-reader compatibility/evolution rules;
- GI-1 establishes a governed knowledge foundation with authorized exact-version source resolution,
  bounded reads and actual-byte digest verification before any agent or retrieval adapter is
  connected;
- GI-1A connects that gate to clean private evidence uploads with canonical source identity,
  initiative owner/admin authorization and exact S3 object resolution, without exposing a content
  endpoint or model path;
- keep agent/model output untrusted and route every accepted recommendation through existing human
  or deterministic governance decisions.

### Outcome: enterprise identity is validated beyond local testing

- validate Microsoft Entra login in a real tenant;
- validate Conditional Access behavior and failure modes;
- test group overage, guest policy and authorization mappings with real directory data;
- document and exercise provider-side account, session and role revocation procedures.

### Outcome: audits receive portable business evidence

- export a scoped evidence package by initiative, system and review round;
- include decisions, versions, digests, references and verification instructions;
- define redaction and minimization rules for export;
- define retention and legal-hold integration points.

### Outcome: runtime assurance gains historical depth

- retain bounded, privacy-safe observations suitable for explicit time-window analysis;
- distinguish policy/authorization violations from statistical model-quality drift;
- define evidence-backed control-effectiveness measures without inventing unavailable signals;
- connect alert routing and escalation to organization-specific operational ownership.

### Outcome: governance integrates with the enterprise lifecycle

- expose stable APIs/webhooks for CMDB, data catalogs, CI/CD and GRC;
- import build, test and evaluation evidence without trusting arbitrary payloads;
- define idempotency and replay behavior;
- map external identifiers without making external systems the domain authority.

## Later - scale policies and organizational use

### Outcome: sector-specific governance without forking the core

- add overlays for financial services, healthcare, HR and knowledge systems;
- keep baseline control IDs stable;
- define precedence and conflict rules for overlays;
- publish reference mappings to applicable standards and regulations.

### Outcome: support larger portfolios and multiple teams

- establish multi-tenant or organizational-boundary strategy;
- define horizontal scaling and background-job architecture;
- introduce durable notifications and review queues;
- add portfolio segmentation and delegated administration;
- define archival and data-lifecycle automation.

## Decision gates for roadmap items

A roadmap item should move into implementation only when it has:

1. a clear owner and user outcome;
2. an ADR or documented architectural direction when material;
3. explicit data-minimization and authorization rules;
4. failure and recovery behavior;
5. measurable acceptance criteria;
6. a documentation and migration plan.

## Explicitly out of scope without a new product decision

- automated legal opinions;
- unreviewed LLM-based governance approval;
- silent reuse of old approvals after material scope change;
- storing prompts, documents or model responses by default for observability;
- allowing external routers or integrations to expand governance authority;
- treating a deterministic demo adapter as evidence of a live third-party integration.

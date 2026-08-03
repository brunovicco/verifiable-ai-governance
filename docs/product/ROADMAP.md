# Product roadmap

- **Status:** Current
- **Owner:** Product and architecture
- **Last reviewed:** 2026-08-03
- **Review trigger:** Quarterly planning or material dependency change

This roadmap communicates outcomes. The technical backlog remains authoritative for
individual stories and tasks.

## Now - prove the complete reference workflow

### Outcome: a reviewer can understand the project in minutes

- maintain an executive-first English README and Portuguese translation;
- add a real product screenshot and short demo recording;
- keep the capability matrix aligned with code;
- publish a reproducible demo scenario;
- add documentation ownership and review metadata.

### Outcome: enterprise identity is validated beyond local testing

- validate Microsoft Entra login in a real tenant;
- validate Conditional Access behavior and failure modes;
- test group overage, guest policy and authorization mappings with real directory data;
- document provider-side account, session and role revocation procedures.

### Outcome: security posture is reviewable

- adopt and maintain the threat model;
- enable a private vulnerability reporting channel;
- select a repository license;
- add dependency and container security scanning where appropriate;
- document secret rotation and production key-management expectations.

## Next - connect governance to operational evidence

### Outcome: runtime behavior feeds assurance

- ingest sanitized telemetry from runtime adapters;
- correlate runtime events with system, model, agent and approved-scope identifiers;
- calculate drift only from defined observations and thresholds;
- create control-effectiveness measures backed by evidence sources;
- define SLOs and alert routing.

### Outcome: audits receive portable evidence

- export an evidence package with manifest, versions, decisions, digests and references;
- support scoped exports by initiative, system and review round;
- include verification instructions and redaction rules;
- define retention and legal-hold integration points.

### Outcome: governance integrates with the enterprise lifecycle

- expose stable APIs or webhooks for CMDB, data catalogs, CI/CD and GRC;
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
- allowing external routers or integrations to expand governance authority.

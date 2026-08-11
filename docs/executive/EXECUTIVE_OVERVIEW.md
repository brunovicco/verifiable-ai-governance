# Executive overview

- **Status:** Current
- **Owner:** Project maintainer
- **Last reviewed:** 2026-08-11
- **Review trigger:** Material product or maturity change

## Executive summary

Verifiable AI Governance is a vendor-neutral reference platform for operationalizing AI
governance. It connects business intake, deterministic risk/control policy, structured
assessments, independent approvals, evidence, AI asset assurance, runtime authorization,
enforcement, telemetry, governed response and release assurance.

The central design principle is that a governance decision should be more than a status field. It
should remain bound to:

- the facts and policy version used to classify the initiative;
- the exact model/agent scope reviewed by independent approvers;
- the evidence available at decision time;
- the authorization actually presented at runtime;
- the runtime outcome and any trusted violation evidence;
- the operational response taken afterward;
- a preserved and independently verifiable history.

## Business problem

Organizations commonly govern AI through separate processes and tools. Business teams submit
documents, technical teams maintain inventories, security tracks findings, privacy runs impact
assessments and runtime teams operate models without one evidence chain.

This fragmentation creates recurring risks:

1. unclear accountability and ownership;
2. inconsistent risk classification;
3. approvals not tied to a versioned technical scope;
4. changes after approval without reassessment;
5. evidence stored without integrity/provenance;
6. runtime use that exceeds approved data, model or autonomy boundaries;
7. runtime denials that disappear into application logs instead of governance evidence;
8. weak visibility into incidents, assurance state and governed containment;
9. release claims that cannot be reconstructed from frozen source.

## Product response

The platform provides:

- a business-facing intake portal;
- deterministic and explainable preliminary risk classification;
- a versioned catalog of declarative controls;
- structured AI impact, privacy and international-processing assessments;
- independent multidisciplinary approval gates;
- immutable review rounds and explicit resubmission;
- an operational inventory of AI systems, models and agents;
- independent scope reviews for models and agents;
- signed, scope-bound runtime authorization;
- approved-scope model-group routing and fail-closed revalidation;
- persisted trusted runtime violation evidence;
- authenticated, sanitized runtime telemetry ingestion;
- bounded runtime assurance plus governed containment/restoration paths;
- verified evidence uploads and tamper-evident audit history;
- incidents, temporary exceptions and remediation;
- release security/provenance/runtime/clean-install evidence with offline verification.

## Strategic differentiation

### Governance as executable policy

Risk and control applicability are computed by deterministic, versioned code rather than hidden
language-model judgment. Decisions can be tested with positive/negative scenarios and reproduced
from normalized facts.

### Assurance bound to scope

Model and agent reviews capture canonical scope. Material changes invalidate relevant authorization,
and dependent agents cannot silently inherit a broader model scope.

### Governance connected to runtime

The runtime path does not trust an external router merely because it returned a result. Governance
revalidates approved scope and can preserve trusted fail-closed denials as violation evidence.
Sanitized operational telemetry then feeds explicit assurance rather than invented dashboard
metrics.

### Governed response

A runtime problem is not complete as a dashboard signal. The reference path includes incidents and
runtime controls for containment/restoration, with correlation and audit evidence.

### Release evidence as a product property

The release process binds frozen component commits to SBOM/security policy, deterministic
provenance, runtime benchmark/SLO and clean-install evidence. A final candidate root can be
verified offline before GitHub OIDC/Sigstore attestations are considered.

### Evidence-aware and privacy-minimized design

Uploaded evidence is bounded, signature-validated, hashed, malware-scanned and stored privately.
Runtime telemetry prefers stable IDs, categories, bounded metrics and digests; prompts and model
payloads are not required by default.

### Transparent limitations

The repository distinguishes deterministic demo fixtures from live cross-repository proof. Real
Microsoft Entra/Conditional Access validation remains environment-specific. Long-horizon
statistical drift analytics, enterprise-wide control-effectiveness scoring and portable business
audit-package export remain partial/planned rather than being inferred.

## Intended users

- AI Governance and Responsible AI teams;
- enterprise architecture and AI platform engineering;
- security, privacy, legal, compliance and data governance;
- product owners and business requesters;
- model owners and runtime operators;
- internal audit and risk committees.

## Technology and engineering posture

The implementation uses a Next.js portal, FastAPI application, PostgreSQL, S3-compatible private
storage and ClamAV, with explicit adapters for identity, external routing, telemetry and runtime
control. Inner application/domain rules remain separated from infrastructure boundaries.

Engineering controls include strict typing, linting, automated tests, repository-hygiene checks,
explicit database migrations from an empty database, optimistic concurrency, transaction-scoped
audit, fail-closed configuration, verified backup/restore and coordinated release evidence.

## Maturity statement

The repository is a functional, production-oriented reference implementation rather than a
certified commercial product. Core governance, verified evidence, asset assurance, runtime
authorization/enforcement, sanitized telemetry, bounded runtime assurance, governed response and
release-evidence tooling are implemented reference paths.

Real Microsoft Entra tenant/Conditional Access validation, broader historical statistical drift,
enterprise control-effectiveness analytics, portable business audit-package export and enterprise
CMDB/data-catalog/GRC integrations remain environment-specific, partial or planned.

## What this project demonstrates

For technical leadership and hiring evaluation, the repository demonstrates the ability to combine:

- AI governance and responsible AI principles;
- Clean/hexagonal architecture and transactional backend engineering;
- identity, authorization and least privilege;
- model and agent lifecycle governance;
- evidence integrity and auditability;
- runtime policy enforcement and fail-closed evidence;
- privacy-minimized operational assurance;
- incident response and governed actuation;
- software supply-chain/release evidence;
- operational resilience and transparent product scoping.

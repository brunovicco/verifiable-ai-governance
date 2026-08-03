# Executive overview

- **Status:** Current
- **Owner:** Project maintainer
- **Last reviewed:** 2026-08-03
- **Review trigger:** Material product or maturity change

## Executive summary

Verifiable AI Governance is a vendor-neutral reference platform for operationalizing AI
governance. It connects business intake, risk classification, controls, structured
assessments, independent approvals, evidence, AI asset assurance, runtime policy
decisions, monitoring and incident response.

The central design principle is that a governance decision should be more than a status
field. It should remain bound to:

- the facts and policy version used to classify the initiative;
- the exact scope reviewed by independent approvers;
- the evidence available at decision time;
- a preserved decision history;
- the operational conditions enforced at runtime.

## Business problem

Organizations commonly govern AI through separate processes and tools. Business teams
submit documents, technical teams maintain inventories, security tracks findings,
privacy runs impact assessments and runtime teams operate models without a shared chain
of evidence.

This fragmentation creates recurring risks:

1. unclear accountability and ownership;
2. inconsistent risk classification;
3. approvals that are not tied to a versioned technical scope;
4. changes after approval without reassessment;
5. evidence stored without integrity or provenance;
6. runtime use that exceeds approved data, cost, autonomy or model boundaries;
7. weak visibility into incidents, exceptions and overdue reviews.

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
- runtime enforcement before model-group routing;
- verified evidence uploads and tamper-evident audit history;
- incidents, emergency restriction, temporary exceptions and remediation;
- portfolio metrics for risk, coverage, cycle time and operational status.

## Strategic differentiation

### Governance as executable policy

Risk and control applicability are computed by deterministic, versioned code rather than
hidden language-model judgment. Decisions can be tested with positive and negative
scenarios and reproduced from normalized facts.

### Assurance bound to scope

Model and agent reviews capture a canonical digest of the approved scope. Material
changes invalidate the relevant approval, and model changes can invalidate dependent
agents.

### Governance connected to runtime

Before an external routing decision is accepted, the platform verifies asset status,
review validity, data class, approved model groups and cost limits. The external router
cannot expand governance authority.

### Evidence-aware design

Uploaded evidence is size-limited, signature-validated, hashed, malware-scanned and
stored in private object storage. Audit records preserve metadata and decision context
without copying sensitive file content into logs or relational tables.

### Transparent limitations

Unavailable capabilities such as real drift or control-effectiveness calculation are
represented as unavailable rather than inferred or fabricated. Enterprise identity
integration is separated from local demonstration mode, and real-tenant validation
remains explicit.

## Intended users

- AI Governance and Responsible AI teams;
- enterprise architecture and AI platform engineering;
- security, privacy, legal, compliance and data governance;
- product owners and business requesters;
- model owners and runtime operators;
- internal audit and risk committees.

## Technology and engineering posture

The implementation uses a Next.js portal, FastAPI application, PostgreSQL, S3-compatible
private storage and ClamAV. The architecture isolates domain and application rules from
HTTP, persistence, identity providers and external routers through internal ports and
adapters.

Engineering controls include strict typing, linting, automated tests, explicit database
migrations, optimistic concurrency, transaction-scoped audit, fail-closed startup,
configuration through environment variables and verified backup/restore procedures.

## Maturity statement

The repository is a functional, production-oriented reference implementation rather
than a certified commercial product. Core governance, evidence, asset assurance,
runtime routing enforcement and operational response are implemented. Validation in a
real Microsoft Entra tenant, production telemetry ingestion, drift calculation,
control-effectiveness measurement and enterprise-system integrations remain future or
environment-specific work.

## What this project demonstrates

For technical leadership and hiring evaluation, the repository demonstrates the ability
to combine:

- AI governance and responsible AI principles;
- Clean/hexagonal architecture and transactional backend engineering;
- identity, authorization and least privilege;
- model and agent lifecycle governance;
- evidence integrity and auditability;
- runtime policy enforcement;
- operational resilience and incident response;
- transparent product scoping and technical documentation.

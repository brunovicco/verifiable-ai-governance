# Demonstration guide

- **Status:** Current
- **Owner:** Project maintainer
- **Last reviewed:** 2026-08-03
- **Review trigger:** User-flow, seed-data or command change

## Goal

Demonstrate that governance decisions remain connected across intake, risk, controls,
approvals, evidence, AI assets, runtime enforcement and operations.

The recommended walkthrough is designed for a 10–15 minute technical or executive demo.

## Prerequisites

- Docker Desktop;
- ports 3000 and 8000 available;
- optional alternative host port for PostgreSQL when 5432 is occupied.

## Start the environment

```bash
cp .env.example .env
docker compose up --build
```

If PostgreSQL port 5432 is occupied:

```bash
POSTGRES_PORT=55432 docker compose up --build
```

Open:

- portal: `http://localhost:3000`;
- API documentation: `http://localhost:8000/docs`.

Wait for ClamAV to become ready before demonstrating evidence uploads. The application
should reject uploads with a service-unavailable response while scanning is not ready.
This is expected fail-closed behavior.

## Seed representative scenarios

Against a newly migrated database:

```bash
make seed-demo
```

The seed uses application services rather than direct fixture insertion. It creates
representative lifecycle states, risk tiers, assessment types and evidence patterns.

## Walkthrough A - executive overview

### 1. Portfolio dashboard

Show:

- distribution of residual risk;
- assessment coverage;
- review cycle-time samples;
- incidents and overdue remediation;
- temporary exceptions;
- model-routing outcomes;
- expired or missing asset reviews;
- explicit unavailable indicators for metrics that do not yet have source data.

Executive message: the dashboard distinguishes measured facts from unavailable
capabilities.

### 2. Initiative portfolio

Open initiatives in different states. Explain that lifecycle state, risk tier and
current review status are separate dimensions.

### 3. One high-risk initiative

Show:

- business purpose and owner;
- preliminary risk breakdown;
- required structured assessments;
- applicable controls and explanations;
- multidisciplinary approval gates;
- review history.

Executive message: governance requirements are derived from normalized facts and an
identified policy version.

## Walkthrough B - technical assurance

### 1. Create or inspect an initiative

Use a scenario with:

- restricted or sensitive data;
- regulated context;
- international processing;
- agentic execution;
- external users or high-impact decisions.

Show that the policy engine raises risk and requires additional gates and documents.

### 2. Structured assessments

Open the AI impact, privacy and international-processing assessments. Highlight:

- explicit schema and version;
- draft ownership;
- expected-version mutation;
- residual-risk declaration;
- immutable state after submission;
- sensitive answers excluded from general audit logging.

### 3. Evidence upload

Upload an allowed demonstration file and show:

- metadata rather than internal bucket coordinates;
- SHA-256 digest;
- scan result;
- private storage behavior.

Explain that URI references supplied in a decision are not equivalent to verified
uploaded artifacts.

### 4. Independent review and resubmission

Demonstrate:

1. owner submits the initiative;
2. a reviewer requests changes;
3. the prior round remains preserved;
4. assessments reopen explicitly;
5. facts are corrected and policy is recalculated;
6. a new review round is created without reusing old approvals.

### 5. Model and agent registry

Open an approved initiative and inspect its AI system, model and agent records.
Highlight:

- models require Architecture review;
- agents require Security review;
- owner cannot self-approve;
- approved scope has a canonical digest and review validity;
- material changes invalidate approval;
- model changes can invalidate dependent agents.

### 6. Runtime routing decision

Use the API documentation or the portal action that requests a model-routing decision.
Explain the sequence:

1. validate operational system and current agent review;
2. calculate eligible approved models and groups;
3. validate data class and cost boundaries;
4. persist a pending attempt;
5. call the external policy router with minimized operational metadata;
6. re-read and verify that the registry scope did not change;
7. accept only a group that still maps to an eligible approved model;
8. persist allowed, blocked or dependency-unavailable outcome.

### 7. Incident and kill switch

Show an incident, remediation target and emergency restriction. Explain that an
operational restriction is distinct from account revocation at the identity provider
and should be used as a platform-level containment control.

## Suggested talking points for recruiters and CTOs

- “The policy layer is deterministic; an LLM does not decide governance approval.”
- “Every material change has a version and a reassessment path.”
- “Approvals are bound to canonical technical scope, not only a ticket status.”
- “The external model router can narrow options but cannot expand approved authority.”
- “Unavailable evidence or security dependencies fail closed.”
- “The repository separates implemented, partial and planned capabilities.”

## Reset

To stop services without deleting persisted data:

```bash
docker compose down
```

Delete volumes only when a full local reset is intentional:

```bash
docker compose down -v
```

Do not use volume deletion as an update procedure for an environment containing data.

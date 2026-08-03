# Observability

- **Status:** Current design with planned runtime ingestion
- **Owner:** Platform engineering and operations
- **Last reviewed:** 2026-08-03
- **Review trigger:** New dependency, metric, dashboard or runtime adapter

## Objectives

Observability must answer:

- Is the governance platform available and correct?
- Are security and policy dependencies healthy?
- Are reviews, incidents and exceptions progressing within expectations?
- Are models and agents operating within approved scope?
- Is collected telemetry proportionate and privacy-preserving?

## Three levels

### Platform operation

- availability and error rate;
- latency and throughput;
- database pool and query health;
- migration status;
- object-storage and malware-scanner health;
- OIDC/JWKS and Graph dependency health;
- external router latency and failure;
- backup and restore-test status.

### Model governance

- model version and region;
- review state and expiry;
- eligible routing group;
- blocked routing decisions and reasons;
- data-class incompatibility;
- cost or latency boundary rejection;
- future quality, groundedness, safety and drift evidence.

### Agent governance

- approved agent scope and review validity;
- allowed models and tools;
- autonomy and human-approval conditions;
- blocked actions and reasons;
- cost, time and step limits;
- incident and kill-switch state;
- future sanitized plan, delegation and tool-decision evidence.

## Logging principles

Use structured logs with:

- timestamp;
- service and environment;
- request or correlation ID;
- stable entity IDs;
- event category and outcome;
- dependency name;
- duration and status code;
- policy/catalog version or digest when relevant.

Exclude by default:

- bearer tokens and credentials;
- prompts and model responses;
- uploaded file content;
- full assessment answers;
- private object-storage coordinates;
- full directory group lists;
- personal data not required for the event.

## Recommended metrics

### API

- request count by route group and result class;
- latency percentiles;
- 4xx/5xx rate;
- optimistic-concurrency conflict count;
- authorization denial count by reason category;
- emergency-blocked request count.

### Database

- connection utilization;
- query latency;
- transaction rollback count;
- migration revision mismatch;
- audit append failures.

### Evidence pipeline

- upload attempts and accepted count;
- rejected size/type/signature count;
- malware detection count;
- scanner unavailable count;
- storage write/delete compensation failures;
- average scan latency.

### Identity and directory

- token validation failures by safe category;
- JWKS refresh failure;
- Graph latency and throttling;
- group-overage resolution count;
- authorization-cache hit/miss/expiry/invalidation;
- authorization-catalog digest changes.

### Governance workflow

- initiatives by status and risk tier;
- required versus submitted assessments;
- gates pending, approved, rejected and not required;
- average review-round duration with sample count;
- overdue asset reviews;
- residual-risk distribution.

### Runtime routing

- pending, allowed, blocked and dependency-unavailable outcomes;
- blocked reason distribution;
- router latency;
- registry-scope-changed count;
- returned-unapproved-group count;
- cost/data-class rejection count.

### Incidents and exceptions

- open incidents by severity;
- overdue remediation;
- mean time to acknowledge and resolve when data exists;
- active and expiring exceptions;
- kill-switch activation and restoration events.

## Tracing

Trace context should propagate across:

```text
Browser/API request
  → application use case
    → database transaction
    → identity/Graph, scanner/storage or model-router dependency
      → final audit and response
```

Trace attributes must follow the same minimization rules as logs.

## Dashboards

Recommended dashboards:

1. platform health;
2. identity and authorization;
3. evidence pipeline;
4. governance portfolio;
5. model/agent assurance;
6. runtime routing outcomes;
7. incidents and exceptions;
8. backup and recovery assurance.

## Alerts

Alert only on actionable conditions with an owner and runbook, including:

- API or database unavailability;
- failed or stuck migration;
- ClamAV unavailable beyond startup allowance;
- object-storage write or compensation failure;
- abnormal token-validation or authorization-denial spike;
- Graph/JWKS/router dependency failure above threshold;
- audit append or chain-verification failure;
- overdue critical remediation;
- active critical kill switch or unexpected restoration;
- backup or restore-assurance failure.

## SLO examples to define organizationally

The repository should not invent production targets. Adopting organizations should set:

- API availability and latency;
- evidence-processing completion time;
- maximum authorization-cache staleness;
- review and incident service-level objectives;
- backup completion and restore-test frequency;
- alert acknowledgement and resolution targets.

Every displayed average should show its sample count. Missing source data should produce
“unavailable”, not zero or an estimated success value.

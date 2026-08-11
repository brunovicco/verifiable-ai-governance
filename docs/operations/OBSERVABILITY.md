# Observability

- **Status:** Current reference implementation; production thresholds are deployment-specific
- **Owner:** Platform engineering and operations
- **Last reviewed:** 2026-08-11
- **Review trigger:** New dependency, metric, dashboard or runtime adapter

## Objectives

Observability must answer:

- Is the governance platform available and correct?
- Are security and policy dependencies healthy?
- Are reviews, incidents and exceptions progressing within expectations?
- Are models and agents operating within approved scope?
- What bounded runtime observations support the current assurance state?
- Is collected telemetry proportionate and privacy-preserving?

The repository now includes authenticated sanitized runtime-telemetry ingestion and bounded
runtime-assurance evaluation. This does not remove the requirement for adopting organizations to
choose meaningful SLOs, thresholds, retention and alert ownership.

## Three levels

### Platform operation

- availability and error rate;
- latency and throughput;
- database pool and query health;
- migration status;
- object-storage and malware-scanner health;
- OIDC/JWKS and Graph dependency health;
- external Router latency and failure;
- backup and restore-test status.

### Model governance

- model version and region;
- review state and expiry;
- eligible routing group;
- blocked routing decisions and reasons;
- trusted runtime violation code/digest;
- data-class or approved-scope incompatibility;
- runtime latency/availability observations where emitted;
- bounded assurance state from defined observations;
- future domain-specific quality/groundedness and long-horizon statistical drift evidence.

### Agent governance

- approved agent scope and review validity;
- allowed models and tools;
- autonomy and human-approval conditions;
- authenticated runtime telemetry bound to the governed agent identity;
- blocked actions and reasons;
- runtime-control/containment state;
- incident and restoration state;
- future domain-specific plan/delegation evidence where explicitly minimized and approved.

## Runtime telemetry boundary

Runtime telemetry is designed to be useful without treating prompt capture as an observability
requirement. The ingestion path prefers bounded metadata such as:

- stable governed entity identifiers;
- correlation/request identifiers;
- event category and outcome;
- latency/availability values;
- policy/authorization/violation identifiers or digests when applicable;
- timestamps and source identity.

Telemetry ingestion is authenticated per governed agent and validates bounded contracts before
persistence. It must not be expanded into a free-form event sink.

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

### API and persistence

- request count by route group and result class;
- latency percentiles;
- 4xx/5xx rate;
- optimistic-concurrency conflict count;
- database connection/query health;
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

### Identity and authorization

- token validation failures by safe category;
- JWKS refresh failure;
- Graph latency and throttling;
- authorization-cache hit/miss/expiry/invalidation;
- authorization-catalog digest changes;
- emergency-blocked request count.

### Governance workflow

- initiatives by status and risk tier;
- required versus submitted assessments;
- gates pending, approved, rejected and not required;
- review-round duration with sample count;
- overdue asset reviews;
- residual-risk distribution.

### Runtime routing and assurance

- pending, allowed, blocked and dependency-unavailable outcomes;
- trusted violation count by bounded reason code;
- Router latency;
- registry/scope-change rejection count;
- returned-unapproved-group count;
- authenticated telemetry accepted/rejected count;
- stale/missing telemetry required by an assurance rule;
- assurance state transitions by bounded category;
- benchmark latency/availability and SLO verdict for release evidence.

### Incidents and governed actuation

- open incidents by severity;
- overdue remediation;
- mean time to acknowledge/resolve when enough observations exist;
- active and expiring exceptions;
- containment activation/restoration events;
- runtime-control dependency failures.

## Tracing

Trace context should propagate across:

```text
Browser/API request
  → application use case
    → database transaction
    → identity/Graph, scanner/storage or Policy Model Router
      → runtime telemetry / governed response where applicable
        → final audit and response
```

Trace attributes must follow the same minimization rules as logs/telemetry.

## Dashboards

Recommended dashboards:

1. platform health;
2. identity and authorization;
3. evidence pipeline;
4. governance portfolio;
5. model/agent assurance;
6. runtime routing and violation outcomes;
7. runtime assurance and governed-actuation state;
8. incidents and exceptions;
9. backup/recovery assurance;
10. release benchmark/SLO evidence.

## Alerts

Alert only on actionable conditions with an owner and runbook, including:

- API or database unavailability;
- failed or stuck migration;
- ClamAV or object-storage failure;
- abnormal authentication/authorization denial spike;
- Graph/JWKS/Router/runtime-control dependency failure above an approved threshold;
- audit append or chain-verification failure;
- stale required runtime telemetry;
- blocked/critical runtime assurance state when an owning team has defined response;
- overdue critical remediation;
- unexpected containment restoration;
- backup or restore-assurance failure.

## SLOs and thresholds

The repository includes benchmark/SLO evidence for its release reference path, but an adopting
organization must define production objectives for its own environment, including:

- API availability and latency;
- runtime routing and telemetry availability/latency;
- maximum accepted telemetry staleness;
- evidence-processing completion time;
- maximum authorization-cache staleness;
- review and incident objectives;
- backup completion and restore-test frequency;
- alert acknowledgement and resolution targets.

Every displayed average should show its sample count. Missing source data should produce
“unavailable” or an explicit assurance failure according to policy, never zero or a fabricated
success value.

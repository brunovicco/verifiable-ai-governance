# ADR 0039 — Deterministic governed runtime-response recommendations

## Status

Accepted.

## Context

P1.8a converts sanitized runtime telemetry into deterministic Runtime Assurance
evidence. P1.8b explicitly promotes breached evidence into the existing Incident
lifecycle with deduplication and severity escalation.

The next governance boundary is operational advice. A breach or an incident may
justify investigation, containment preparation, or consideration of an emergency
kill switch. Conflating advice with execution would create an unsafe control path
and would weaken segregation between evidence, governance decision, and runtime
actuation.

## Decision

P1.8c introduces an append-only, deterministic response recommendation set for one
Runtime Assurance incident promotion.

Generation is explicit and restricted to the AI System owner or an administrator.
Each promotion may have at most one recommendation set.

The rule catalog is closed and versioned as:

- policy ID: `runtime-assurance-response`
- policy version: `1.0`

The generated actions are limited to:

- `investigate_failures`
- `investigate_latency`
- `prepare_containment`
- `consider_kill_switch`
- `monitor_recovery`

`consider_kill_switch` is emitted only when the current incident severity is
`critical`, the Agent declares an available kill switch, and the kill switch is not
already engaged.

The recommendation record freezes the incident version/status/severity and Agent
kill-switch state used by the evaluator. A canonical SHA-256 digest binds the source
promotion/evaluation evidence, rule catalog, structural snapshot, actions, and
controlled rationale codes.

## Safety boundary

A recommendation is advisory evidence only.

P1.8c does not:

- engage or restore a kill switch;
- write Runtime Control transitions;
- revoke Runtime Authorization;
- mutate the Incident;
- invoke Policy Model Router;
- invoke an LLM;
- execute remediation;
- accept arbitrary actuator fields from the API.

A closed Incident cannot receive a new response recommendation.

## Consequences

Runtime-response guidance is now reproducible and auditable while preserving the
existing human-governed control path. Future automation requires a separate ADR,
authorization model, and explicit control-plane design.

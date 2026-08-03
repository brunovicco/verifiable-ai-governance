# ADR 0005 - Declarative control catalog

- Status: accepted
- Date: 2026-07-31

## Context

The framework needs to link risk, control, implementation, and evidence without
hardcoding each control into routers or portal components. It also needs to explain
why a control applies and identify the version used in the decision.

## Decision

- maintain a baseline catalog of 25 controls in YAML inside `policy-engine`;
- validate the file with immutable Pydantic contracts and `extra=forbid`;
- require unique IDs, requirements, evidence, and unambiguous applicability rules;
- evaluate risk, flag, impact, data, autonomy, and hosting selectors through
  deterministic, I/O-free functions;
- return a result and reasons for every control, including non-applicable ones;
- derive the report on query instead of persisting a copy;
- expose the catalog and evaluation through ports defined in the application layer;
- load the catalog once per process and allow override via `CONTROL_CATALOG_PATH`;
- fail closed for a missing file, invalid YAML, an incompatible schema, duplicate IDs,
  or a count different from the expected baseline.

The design applies Open/Closed for adding or adjusting controls that use the existing
selectors, Single Responsibility across schema, loader, evaluator, use case, and UI,
and Dependency Inversion in the API integration.

## Twelve-Factor

The default catalog is policy versioned alongside the code. Organizations can attach
an external configuration via environment variable, without changing the image.
Evaluation is stateless, the YAML dependency is declared in the lockfile, and the
report identifies the policy version that produced the result.

## Consequences

- a catalog change can be reviewed as code and tested in isolation;
- new selector types require explicit evolution of the contract and the evaluator;
- applicability does not equal control implementation or compliance;
- the current report uses facts declared by the initiative and will need to
  incorporate evidence and effectiveness status at a later stage.

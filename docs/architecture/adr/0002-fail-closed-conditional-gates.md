# ADR 0002 - Conditional gates and fail-closed

- Status: accepted
- Date: 2026-07-31

## Context

Requiring the same approvals for every case creates unnecessary bureaucracy; omitting
areas based on implicit rules creates a risk of improper promotion.

## Decision

The policy engine evaluates all areas and records each one as `pending` or
`not_required`, with justification. Incomplete state, an inconsistent rule, a
conflicting version, a missing role, or an unapproved gate blocks promotion.

The owner cannot approve their own initiative. For high or critical risk, the same
person cannot approve more than one required area.

## Consequences

- the absence of a gate becomes explainable and auditable;
- stricter policies may increase approval time;
- future exceptions will need their own entity, deadline, compensating controls, and
  committee approval, with no direct bypass of status.

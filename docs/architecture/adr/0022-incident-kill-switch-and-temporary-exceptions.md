# ADR 0022 - Incidents, kill switch, and temporary exceptions

## Status

Accepted.

## Date

2026-08-02.

## Context

The P1 backlog called for "Incidents, kill switch, temporary exceptions, and remediation
plan" as a native platform feature, not a wrapper around an external project. An
`Incident` table already existed in the schema (created by the initial `create_all()` in
migration 0001), with `title`, `severity`, `status`, `description`, `detected_at`,
`owner_id`, and `containment`, but no domain, application, adapter, router, or schema -
it was prepared, not built. `Agent.kill_switch_enabled` already carried a real but
narrow meaning: `review_agent_scope()` requires the field to be `true` to approve an
agent's scope, but nothing in the code executed that stop at runtime.

ADR 0002 had already committed this platform to a specific design for a future
"exception": its own entity, deadline, compensating controls, and committee approval,
with no direct bypass of status. The RACI already defined "Manage incident" with
Business as accountable and Security/DevOps as executors, plus the segregation rule
"an exception is not approved by the same role that requests or implements the
exception." The governance principle "contestability and remediation when there is
material impact" was also already declared, with no corresponding data model.

## Decision

The `domain/incidents.py` module models a linear, explicit lifecycle:
`open → contained → remediating → closed`, validated by a map of allowed transitions.
Closing an incident requires a complete remediation plan (owner, deadline, and
description) already on record - the same "do not accept an incomplete state"
discipline already used in `review_model_scope`/`review_agent_scope`.

The runtime kill switch is a new action, distinct from the reviewed declaration: the
agent gains `kill_switch_engaged`, `kill_switch_engaged_at`, and
`kill_switch_engaged_by`, separate from `kill_switch_enabled`. Engaging the kill switch
requires that the agent has already declared the capability during Security review and
that the incident is not closed; restoring requires a currently engaged switch. This
preserves the existing meaning of `kill_switch_enabled` instead of overlaying new
behavior onto it.

Temporary exceptions (`PolicyException`) are always tied to an incident, with
`purpose`, `scope_description`, `compensating_controls`, and `expires_at` all required -
the four elements required by ADR 0002 and by the "explicit purpose, access, retention,
and approval" language already used for telemetry exceptions. The persisted status
(`pending`/`approved`/`rejected`/`revoked`) is never rewritten by the passage of time;
validity (`pending`/`active`/`expired`/`rejected`/`revoked`) is computed at read time by
comparing `expires_at` to `now`, following the same pattern as `asset_review_state`.
Deciding an exception requires `decided_by != requested_by` - segregation of duties
enforced in the domain, not just documented.

Every mutation of an incident, kill switch, or exception acquires the
`SELECT ... FOR UPDATE OF ai_systems` lock on the involved system before validating
version or state, reusing exactly the per-aggregate transactional mutex already decided
in ADR 0020 - not a second concurrency mechanism.

## Alternatives considered

- **General-purpose exceptions, applicable to any initiative or system without an
  incident:** rejected at this stage because the backlog groups exceptions with
  incidents/kill-switch/remediation, and all existing precedent (ADR 0002, RACI) talks
  about compensating for a risk during an incident, not a permanent policy exemption. A
  general exceptions engine touching the policy engine and every gate is a larger,
  separate piece of work.
- **A new "committee" role to approve exceptions:** rejected because the only role
  primitive beyond owner/admin in this codebase is `ApprovalArea`, tied to the OIDC
  group mapping of the initiative's gate flow. Creating a parallel role just for this
  slice would be disproportionate; administrator approval with mandatory segregation of
  duties is the closest honest approximation, recorded here as a known simplification
  against ADR 0002's "committee approval" language.
- **Kill switch authority restricted to Security/DevOps:** rejected for the same reason
  - it reuses the "system owner or administrator" boundary already used across every
  inventory mutation, instead of inventing a new role carve-out.
- **Persisting only the final result of each attempt, without the initial `pending`
  record:** does not apply to this design the same way it does to model routing, since
  there is no external network call here between intent and result; the write is local
  and synchronous under the same lock.

## Consequences

- `Incident` gains remediation fields (`remediation_owner_id`,
  `remediation_description`, `remediation_due_at`, `resolved_at`) and switches to
  `Enum(RiskTier/IncidentStatus, native_enum=False)` instead of a free `String`;
- `Agent` gains three new runtime kill-switch columns, without changing the meaning of
  `kill_switch_enabled`;
- `PolicyException` is a new table, always tied to an incident;
- exception decisions are restricted to administrators - a simplification to revisit if
  a richer authorization model is adopted;
- no existing model or agent review is invalidated by this migration (unlike 0008): the
  new fields are additive and optional.

## Security and privacy impact

No prompt, document, or execution content is recorded; incidents and exceptions carry
only structured metadata (title, severity, human-supplied free-text description,
deadlines). The hash-chained audit trail records every transition
(`incident.reported`, `incident.contained`, `incident.remediation_plan_set`,
`incident.closed`, `incident.kill_switch_engaged`, `incident.kill_switch_restored`,
`incident.exception_requested`, `incident.exception_decided`,
`incident.exception_revoked`) with actor, entity, and version, without duplicating the
request body. The exception's segregation of duties is enforced in the domain, not just
at the HTTP boundary, so no future adapter can bypass the rule without also bypassing the
architecture test.

## Operational impact

Migration 0009 is purely additive: new nullable columns on `incidents` and `agents`,
plus the `policy_exceptions` table. There is no reprocessing of existing data and no
invalidation of approvals. The feature is always on - unlike opt-in integrations such as
`policy-model-router`, incidents are part of the product core and have no enablement
flag.

The portal exposes reporting, containing, planning remediation, closing, engaging/
restoring the kill switch, and requesting an exception. Deciding and revoking an
exception are administrator-only endpoints with no portal screen in this delivery,
following the same pattern already used for other administrator-only actions on this
platform (emergency access block/restore, authorization cache invalidation), which also
have no UI.

## Follow-up

- add an administrator screen to decide and revoke exceptions once the portal has a
  concept of local administrative identity;
- evaluate a richer approval role to replace the administrator-as-committee
  simplification;
- alert ahead of remediation deadlines approaching expiration, in the same spirit as the
  follow-up already recorded in ADR 0019/0020 for scope reviews;
- consider referencing this feature from the `GOV-AGT-001` catalog control, today
  limited to requiring a documented kill switch;
- add more exhaustive test coverage for the 403/404 paths of
  `get_incident`/`list_incidents` for nonexistent systems, today exercised only by the
  happy path and the authorization case.

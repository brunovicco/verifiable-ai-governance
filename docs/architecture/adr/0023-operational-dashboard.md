# ADR 0023 - Operational dashboard

## Status

Accepted.

## Date

2026-08-02.

## Context

The P1 backlog asked for a "Dashboard of violations, blocked actions, drift, cost, and
overdue reviews." Before designing the aggregation, we checked exactly which of those
five names already have real persisted data on this platform:

- **Blocked actions**: real - `ModelRoutingDecisionEntry.outcome`/`.reason_code` (the
  model routing feature, ADR 0021) already persists every attempt.
- **Overdue reviews**: real - `ReviewableAssetMixin.review_state` already computes
  `not_reviewed`/`current`/`expired` at read time via `asset_review_state()`
  (ADR 0019/0020).
- **Incidents with overdue remediation** and **active exceptions**: real - added by the
  incidents feature (ADR 0022).
- **Cost**: only declared *limits* exist (`Agent.max_cost`,
  `ModelRoutingDecisionEntry.max_cost_usd`), never observed actual spend. No spend table
  exists.
- **Drift**: no persisted data anywhere in the code. It appears only as a column header
  in `packages/document-templates/templates/monitoring-plan.md` and as prose in
  `docs/governance/MONITORING.md`/`STAGE_GATES.md`. It depends on the still-unbuilt
  integration with `ragforge` (evaluations and regressions).

A governance and assurance product cannot fabricate evidence. The design decision
follows directly from that constraint.

`GET /api/v1/systems` (`routers/inventory.py`) already lists every AI system on the
platform, requiring only `CurrentPrincipal` - no ownership check. This already
establishes that portfolio-wide reads, not restricted to an owner, are an existing
authorization pattern in this codebase, not something new to invent.

## Decision

A single endpoint, `GET /api/v1/dashboard`, aggregates four real sources and exposes the
fifth (drift) as explicitly unavailable - never silently omitted nor fabricated.
Authorization reuses exactly the pattern of `GET /api/v1/systems`: any authenticated
principal, with no ownership check, because portfolio oversight is the resource's
purpose.

"Cost" is shown as blocks due to cost limits (`reason_code=cost_limit_exceeded` in
routing decisions), never as spend - the only honest reading available today.

Review and exception validity are recomputed in Python from the same pure functions
already used across the rest of the product (`asset_review_state()`,
`evaluate_exception_state()`), not reimplemented in raw SQL. The adapter
(`adapters/dashboard_persistence.py`) returns only raw facts
(`approved_scope_digest`, `next_review_at`, `risk_tier` / `status`, `expires_at`); the
use case (`application/dashboard.py::BuildDashboardSnapshot`) applies the same already-
tested business rule instead of keeping it in two places that could diverge (for
example, if `MAX_REVIEW_INTERVAL` changes in the future). Incident status counts and
routing outcome counts, being directly persisted fields with no computed rule, are
aggregated with a plain `GROUP BY`.

No database migration is needed: the dashboard is an aggregated read over tables that
already exist because of the routing (ADR 0021) and incidents (ADR 0022) features.

## Alternatives considered

- **Compute review/exception validity in raw SQL for performance:** rejected - it would
  duplicate a business rule that already exists in pure domain code, with a real risk of
  silent divergence between the SQL version and the Python version if the rule changes.
- **Fabricate a "drift" number from a proxy (e.g., count of review invalidations):**
  rejected - a review invalidation measures something else (scope change), and
  presenting it as "drift" would mislead the panel's reader. An assurance product cannot
  invent evidence.
- **Restrict the dashboard to the owner's scope, like most other endpoints:** rejected -
  the purpose of an operational dashboard is precisely portfolio-wide visibility;
  restricting it by ownership would defeat that. The precedent of `GET /api/v1/systems`
  already shows this exception is accepted in this codebase.
- **Metrics with a time window (e.g., "last 30 days"):** deferred to a future delivery;
  v1 is an all-time snapshot, simpler to implement and validate correctly first.

## Consequences

- no new migration, no new frontend dependency (no charting library - the panel uses
  the same `panel`/tables already used throughout the portal);
- review and exception validity are recomputed on every request over every row on the
  platform; acceptable at the current scale, should be revisited (pagination or cache)
  if the number of models/agents/exceptions grows significantly;
- "drift" remains an explicit placeholder until the `ragforge` integration exists;
- the panel has no cache: every load reflects the current state, consistent with the
  principle of never presenting a stale state as current.

## Security and privacy impact

The response contains only aggregated counts - no end-user identifier, prompt or
document content, and no per-system detail beyond what is needed for grouping by risk.
The "any authenticated" authorization is the same already used to list systems; no new
exposure boundary is introduced.

## Operational impact

No migration. The feature is always on, with no enablement flag, just like the
incidents and routing features that feed it.

## Follow-up

- add drift once the `ragforge` integration exists;
- consider metrics with a time window beyond the current all-time snapshot;
- consider pagination or caching if the number of aggregated rows grows;
- link the panel's numbers to filtered views (e.g., clicking "overdue remediations"
  should lead to the list of those incidents).

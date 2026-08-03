# ADR 0019 - Scope reviews for models and agents

## Status

Accepted.

## Date

2026-08-01.

## Context

Registering a provider, version, or tools does not prove that an asset has been
assessed for a specific use. An approved initiative also does not automatically
authorize every associated model or agent. The inventory needs to distinguish
registration from approval, tie the decision to the material scope, and lose that
approval when the scope changes.

The mechanism must work without trusting the frontend, prevent self-approval by the
owner, bound validity according to risk, and preserve evidence without copying
sensitive content into the audit trail.

## Decision

Models and agents stay in `draft` until an independent review. Architecture reviews
models; Security reviews agents. The reviewer must hold the required area and cannot be
the system's owner, nor, for agents, the agent's own owner. The administrative role does
not substitute for this specialized authority or for the separation of duties.

An approved review produces the current projection:

- the reviewer's stable identity and the instant of the decision;
- next review bounded by risk: 365 days for low, 180 for medium, 90 for high, and 30 for
  critical;
- a short evidence reference;
- a SHA-256 digest of canonical JSON covering the entire approved scope.

The model must declare approved use cases, authorized data classes, and an evaluation
baseline. Approved and prohibited use cases must not overlap, and the review cannot
extend past the decommissioning date.

The agent must declare version, region, allowed models, and kill switch. Tools require
explicit permissions; autonomy A2 or higher requires human approval checkpoints; A3 or
higher also requires cost and time limits. All allowed models must be approved and have
a current review; the agent's validity cannot extend past the review of any of those
dependencies.

Any material change clears the review projection and returns the asset to `draft`.
Changing or retiring a model also invalidates approved agents that depend on it.
Changing the system's owner invalidates all linked reviews. Current state lives in the
operational tables; decisions and invalidations remain in the hash-chained log.

## Consequences

- initiative approval and asset approval are different decisions;
- the digest allows comparing the decision against the current scope without recording
  the entire content in the audit trail;
- agents do not stay approved over models that have been changed, retired, or expired;
- expired dates do not physically change the status, but produce `review_state=expired`,
  stop satisfying policy, and block new dependencies until renewal;
- agent records migrated from before this feature receive `unversioned` and
  `unspecified` purely as transition markers, and cannot be approved without an explicit
  update;
- runtime enforcement remains outside this adapter and will be integrated in a later
  delivery.

## Verification

- domain tests cover authority, segregation, cadence, readiness, and digest;
- application tests cover review, cross-asset dependency, and cascading invalidation;
- HTTP contracts validate expected version, timezone-aware date, and bounded reference;
- the portal collects the required metadata and exposes the specialized reviews;
- the migration passes upgrade, downgrade to `0006`, and re-upgrade on real PostgreSQL.

## Follow-up

- integrate decisions with `policy-model-router` for runtime enforcement;
- alert ahead of reviews approaching expiration;
- include expired assets and violations in the operational dashboard;
- replace textual references with optional links to verified evidence.

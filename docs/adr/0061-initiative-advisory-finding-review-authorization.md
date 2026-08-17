# ADR 0061 - Initiative advisory finding review authorization

- **Status:** Accepted
- **Date:** 2026-08-17
- **Decision owners:** Engineering, architecture, security and AI Governance

## Context

ADR 0060 introduced an internal, non-authoritative review boundary for Governance Intelligence
findings. Its consumer-owned `GovernanceFindingReviewAuthorizerPort` deliberately selected no
governed subject or reviewer policy. Consequently, the generic composition remained inert until a
consumer could bind authenticated identity to a concrete subject without weakening the existing
initiative or approval boundaries.

Initiatives already have a canonical UUID identity and a `business_owner_id`. Verified evidence
resolution also uses initiative owner or administrator access for source material. Advisory finding
review needs a first concrete policy that is consistent with that boundary but does not borrow the
segregation-of-duties or authority semantics of formal approval gates.

## Decision

GI-3A defines the initiative as the first concrete subject for advisory finding review.
`subject_id` is the canonical lowercase, hyphenated, non-nil UUID string stored as `Initiative.id`;
prefixed, uppercase, malformed, nil and absent identities are denied.

`SqlAlchemyInitiativeFindingReviewAuthorizer` opens one short-lived read session and selects only
`Initiative.business_owner_id` for the exact subject. It returns `True` only when the initiative
exists and the authenticated actor is either:

- the initiative business owner; or
- an authenticated platform administrator.

Absent initiatives, aliases and unauthorized actors all return the same `False` decision. A
SQLAlchemy failure is translated to `GovernanceFindingReviewDependencyError` without database or
finding details. The read session closes before the independent GI-3 audit transaction starts.

The closed finding type is passed through the authorization port as context, but every current
`GovernanceFindingType` uses the same owner/admin rule. Finding taxonomy does not map to approval
areas and cannot grant authority.

`build_initiative_governance_finding_review` composes this policy with the existing digest-bound,
content-minimized GI-3 audit unit. The builder is internal and is not registered as a FastAPI
dependency, endpoint, task, queue or provider consumer.

Owner review is permitted because a disposition concerns an untrusted advisory finding and does
not approve, reject or authorize the initiative. Any later governed decision continues to use its
existing validation, reviewer-area and segregation-of-duties rules.

## Alternatives considered

### Require an independent approval-area reviewer

Rejected for this boundary. It would make advisory triage look like a formal governance gate and
would couple finding types to authoritative approval roles. Independence remains mandatory where
existing governed use cases require it.

### Prohibit the initiative owner from reviewing advisory findings

Rejected. Owners may triage non-authoritative input about their initiative. The review disposition
cannot mutate initiative state or satisfy an approval.

### Accept arbitrary or prefixed subject identifiers

Rejected. A direct canonical initiative UUID avoids aliases, ambiguous subject classes and
cross-subject authorization mistakes.

### Reuse a request-scoped evidence store

Rejected. Finding review may occur independently of an evidence request. A dedicated minimal
reader keeps its session lifetime and selected fields explicit.

### Add an endpoint together with the concrete policy

Rejected for GI-3A. Delivery still requires idempotency, concurrency, abuse controls, response
semantics and finding-content retention decisions.

## Consequences

- initiative owner/admin review policy is executable rather than left to an arbitrary consumer;
- missing and forbidden initiative subjects remain indistinguishable at the application boundary;
- all finding types remain advisory and receive identical authorization treatment;
- owner review does not imply segregation-of-duties compliance for a later governed action;
- a subject lookup and a separate audit transaction introduce a bounded authorization-to-audit
  timing window;
- other subject classes require separate policies and composition builders.

## Security and privacy impact

The adapter reads only the exact initiative identity and business owner identity. It receives no
finding statement, confidence, sources, provider/model data or source content. Invalid identities
fail before database access, dependency errors are content-free and denial writes no review
receipt. Administrators cannot review a nonexistent initiative.

The audit event remains the minimized ADR 0060 receipt: actor, subject, trace IDs, finding metadata,
candidate digest, disposition, administrator-access fact and time. No full finding or free-form
rationale is persisted. Future delivery must derive `actor_id` and `is_admin` from authenticated,
trusted identity rather than caller-controlled payload fields.

## Operational impact

Each authorized attempt adds one short initiative ownership query before the existing audit write.
No migration, configuration, background worker, external service or new storage is required. A
database outage returns the existing `dependency_unavailable` review failure. Operators must
investigate with content-free actor, subject and correlation identifiers and must not log findings.

## Follow-up

- define idempotency, concurrent review and supersession before delivery exposure;
- decide safe finding-content retention, rendering, deletion and access if an inbox is introduced;
- define separate authorization policies before supporting systems, assessments or controls;
- evaluate whether ownership changes require a stronger transactional snapshot or authorization
  provenance before review becomes externally callable;
- route any accepted recommendation through an existing authoritative use case with its own
  validation, segregation-of-duties and audit policy.

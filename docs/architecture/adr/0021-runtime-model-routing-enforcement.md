# ADR 0021 - Runtime enforcement of policy-model-router decisions

## Status

Accepted.

## Date

2026-08-02.

## Context

ADR 0019 reviews the scope of models and agents, but does not decide which logical model
group a concrete execution should use. ADR 0019 and ADR 0020 already listed, as a
follow-up, integrating these reviews with a runtime routing decider. Without that
integration, nothing prevents a workflow from invoking a model outside the reviewed
scope, and nothing ties an external router's choice to a current Architecture review.

`policy-model-router` is an external service, independent of this platform, that
receives operational metadata for a task (workload, risk, data class, cost and latency
limits) and returns a logical model group or an explicit rejection. It has no access to
prompts, documents, or end-user identity, and does not know this platform's asset review
state. Trusting the router's response alone would let an external service silently
expand the approved scope; trusting only the local review, without consulting the
router, would not meet the goal of deciding at runtime which group to use among those
already approved.

## Decision

The application maintains two deliberately separate authorities. Local governance
(`evaluate_routing_scope`) decides **whether** an agent can operate and **which
reviewed logical groups** are eligible, before any external call: operational system,
agent approved with a current review, at least one eligible model (approved, with a
current review and an explicit `routing_group`, never the migration marker
`unassigned`), a data class authorized by some eligible model, and cost within the
agent's reviewed limit. `policy-model-router` decides **which** of those eligible groups
to use for a specific `workflow_id`/`task_id`.

Each attempt is persisted as `pending` before the external call and finalized as
`allowed`, `blocked`, or `dependency_unavailable` afterward, in two distinct transactions
(persist the intent, then persist the result). A failure between these two transactions
still leaves auditable evidence of what was attempted. The SHA-256 digest of the scope
(the same canonicalization recipe already used by the review digest in ADR 0004) is
captured at the moment of the local check and revalidated against a fresh read of the
registry after the external response; a divergence blocks the decision as
`registry_scope_changed` rather than accepting potentially stale facts.

The call to the router is a single `POST /route`, with no retry: the operation is not
idempotent, and repeating it could produce duplicate decisions or duplicate costs. Any
transport failure, malformed response, a response that does not match the
`workflow_id`/`task_id` sent, a response above the configured maximum size, or a missing
credential configured for the agent is mapped to the typed error
`ModelRouterUnavailable` and finalized as `dependency_unavailable`, translated to
HTTP 503 through the existing `ErrorKind.DEPENDENCY_UNAVAILABLE` category. An explicit
rejection from the router (`outcome=rejected`) is propagated as a block with the
router's own `reason_code`, with `router_rejected` as a stable fallback when the router
does not supply a code.

The group selected by the router is accepted only if it matches the `routing_group` of a
currently eligible model: approved, with a current review, and with the initiative's
data class among its allowed classes. This closes the follow-up from ADR 0019 and
ADR 0020 - the router can never approve a group that governance has not explicitly
reviewed, and the computed validity (`review_state`) is the criterion used, not the
historical status.

## Alternatives considered

- **Trust the router's response alone:** rejected because it would let an external
  service expand the approved scope without local review, breaking this platform's core
  guarantee.
- **Retry the `POST /route` call on transient failure:** rejected because the operation
  is not idempotent; a retry could produce a second, divergent decision for the same
  task with no reliable way to deduplicate on the router side.
- **Validate the scope only before the external call, without revalidating afterward:**
  rejected because a review could expire or an asset could change during the network
  call, approving a runtime action over facts that are already stale.
- **Persist only the final result, without the initial `pending` record:** rejected
  because a process failure during the external call would leave no evidence of the
  attempt at all, contradicting the audit trail required across the rest of the
  platform.

## Consequences

- `routing_group` becomes a first-class reviewed field: an Architecture review of a
  model requires an explicit logical group, and the migration marker `unassigned` is
  rejected both in review and in runtime eligibility;
- every existing model or agent review is invalidated by the migration, because its
  previous digest did not bind `routing_group` (see Operational impact);
- each routing attempt costs two round trips to the database and two commits;
- router credentials are mapped by the exact name of a reviewed agent, never shared
  across agents;
- no prompt or document content is sent to the router, only operational and risk
  metadata already present in the registry.

## Security and privacy impact

The payload sent to the router contains only workload, risk, data class, and estimated
operational limits - never a prompt, document, or end-user identifier. The per-agent
credential (`POLICY_MODEL_ROUTER_API_KEYS_JSON`) never appears in a configuration
`repr()` or in logs. Unavailability, an invalid response, or a missing credential fail
closed as `dependency_unavailable`, never as an implicit approval. The audit trail
records only metadata and provenance (policy, digest, selected group), never the
router's raw response body.

## Operational impact

Migration 0008 adds `routing_group` to `model_assets` with a transition value, and then
forces every already-reviewed model and agent back to `DRAFT` (except those already
`RETIRED`), because no prior review bound the new field to the approved digest. This is
an expected one-time re-review cost at deployment of this change, not a side effect to
fix later. `POLICY_MODEL_ROUTER_ENABLED` is opt-in (`false` by default), so environments
that do not configure the router are unaffected. The external router itself is not
operated by this platform; its availability and decision policy are the responsibility
of the `policy-model-router` service.

## Follow-up

- This decision closes the follow-ups "integrate decisions with `policy-model-router`
  for runtime enforcement" (ADR 0019) and "use `review_state=current` in the
  `policy-model-router` adapter" (ADR 0020).
- Add test coverage for the 403/404 authorization paths of
  `RequestModelRoutingDecision` and `ListModelRoutingDecisions`, and for the listing
  endpoint itself.
- Add dedicated unit test coverage for the immutability and version-conflict guards of
  `SqlAlchemyModelRoutingDecisionStore`, today only exercised indirectly through
  endpoint tests.
- Add test coverage for the case where the scope changes between the router's acceptance
  and the post-call re-read (`registry_scope_changed` after an `accepted`, not only
  before).
- Add test coverage for additional HTTP adapter failure modes (malformed JSON,
  unexpected status such as 500/401, invalid `Content-Length` header).
- Export aggregated metrics of decisions by outcome (`allowed`/`blocked`/
  `dependency_unavailable`) and by `reason_code`, without sensitive identifiers.

# ADR 0015 - Bounded retry for Microsoft Graph reads

## Status

Accepted.

## Date

2026-08-01.

## Context

The Microsoft Graph adapter via OBO already bounded timeout, pagination,
response size, and `Retry-After`, but returned the first occurrence of a `429`
or `5xx` failure to the caller. Transient failures could interrupt the group
resolution used in approvals, while an unrestricted retry could keep
interactive requests open longer, worsen throttling, and increase load on
Graph.

Official Microsoft Graph guidance recommends honoring `Retry-After` on `429`
and using backoff when the header is absent. The integration also needs to
produce enough operational signal to detect throttling without logging token,
user, or directory content.

## Decision

The adapter will retry only idempotent profile and group reads for statuses
`429`, `500`, `502`, `503`, and `504`, plus timeout and transport error. The
total number of attempts is configured via `MICROSOFT_GRAPH_MAX_ATTEMPTS` and
includes the first call.

When a numeric `Retry-After` is present, the adapter will honor the value only
if it is within `MICROSOFT_GRAPH_MAX_RETRY_DELAY_SECONDS`. A larger delay
fails fast and keeps a bounded value for the caller. Without a valid header,
the adapter uses exponential backoff with injectable jitter and a local cap.

The OBO exchange will not be retried automatically. It is a `POST` operation
on the identity provider and does not belong to the explicitly idempotent set
covered by this policy.

The adapter will emit `microsoft_graph_retry`,
`microsoft_graph_retry_deferred`, and `microsoft_graph_retry_exhausted` log
events with operation, status, attempt, and delay. The events will not
contain URL, token, tenant, object ID, profile, groups, or remote body.

## Alternatives considered

- Retry no calls at all: rejected because it turns brief throttling and
  transient failure into immediate unavailability.
- Retry every HTTP operation, including OBO: rejected because it widens the
  scope beyond recognizably idempotent operations.
- Retry indefinitely following `Retry-After`: rejected for blocking
  interactive requests and increasing cascade risk.
- Ignore `Retry-After` and use only local backoff: rejected for contradicting
  the service's explicit throttling signal.
- Adopt the Microsoft Graph SDK just to get automatic retry: rejected at this
  stage because the current HTTP adapter already keeps a reduced surface and
  contract.

## Consequences

Brief transient failures can be absorbed without changing the application's
contract. The operation's maximum duration increases in a bounded way based
on the configured number of attempts, timeouts, and delay budget. The policy
remains testable because sleep and jitter are injectable collaborators.

There is no database migration or new persistence. Cache and revocation are
not resolved by this decision.

## Security and privacy impact

Retry cannot promote a user: if the budget runs out, resolution keeps
failing closed. Invalid responses, divergent identity, and untrustworthy
pagination are not retried as valid transient failures.

Logs are minimized and use only an application-defined operation, status,
attempt, and delay. The API's bearer token, the delegated token, the secret,
IDs, and remote content stay out of telemetry.

## Operational impact

Operations must monitor retry volume, deferred retries, and exhaustion per
operation and status. Attempt and delay values must account for the
endpoint's latency budget; increasing
`MICROSOFT_GRAPH_MAX_RETRY_AFTER_SECONDS` does not increase the allowed
internal delay.

Changes are supplied per environment, in line with Twelve-Factor. Rollback
restores previous values or sets a single attempt, with no schema change.

## Follow-up

- Define a cache with explicit freshness and consistency across replicas.
- Implement auditable invalidation and emergency revocation.
- Handle group overage without following URLs supplied by claims.
- Export aggregated latency, throttling, and stale-identity metrics.
- Validate the policy against a non-production Entra tenant and Conditional
  Access.

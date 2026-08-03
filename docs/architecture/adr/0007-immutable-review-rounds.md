# ADR 0007 - Immutable review rounds and resubmission

- Status: accepted
- Date: 2026-08-01

## Context

An initiative may need corrections requested by Business, Architecture, Security,
Infrastructure, DevOps, Privacy, Legal, Compliance, or Data. Changing the proposal,
assessments, and gates of the original submission would erase the basis for the
decision and make it impossible to explain what content each area reviewed.

It is also necessary to prevent two reviewers from deciding on a stale projection, or
a simultaneous resubmission from creating concurrent rounds.

## Decision

Each submission creates a `ReviewSubmission` with:

- a sequential round number and a review summary;
- a snapshot of the proposal and the assessments at that moment;
- the policy, version, score, and tier used in the evaluation;
- a new set of gates bound exclusively to the round.

`changes_requested` closes the current round, marks any still-pending gates as
`superseded`, and reopens the submitted assessments as new versioned drafts. The owner
first saves the corrected facts, letting the policy recalculate any new required
documents. Then, they correct or create and submit every applicable structured
assessment before resubmitting the initiative. Resubmission re-evaluates the policy
and creates a round; previous approvals are never implicitly reused. `rejected`
remains terminal.

State, authorization, and separation-of-duties rules live in pure Python domain code.
Commands lock the initiative row in the transaction, require `expected_version`, and
convert uniqueness collisions into an explicit conflict. The frontend presents only
the current round's gates and a minimized view of the history.

## Security and privacy

- only the owner, an administrator, or a participating reviewer can view the history;
- full snapshots are not returned by the history endpoint;
- comments and snapshot content are not copied into the audit log;
- snapshots live in PostgreSQL and inherit the database's encryption, backup,
  retention, and access control;
- decisions on stale gates fail closed;
- for high or critical risk, one person does not decide for more than one area in the
  same round.

## Consequences

The trail allows reconstructing the proposal evaluated at each decision and provides a
basis for audit and contestation. The cost is duplicated storage and the need for an
explicit retention policy. Migration downgrade is refused when rounds greater than one
exist, to avoid silently destroying history.

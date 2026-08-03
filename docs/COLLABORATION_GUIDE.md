# Guidance for Work and Codex

## Work

Use for product vision, personas, journeys, interface language, policies,
templates, risk criteria, controls, RACI, stage gates and functional review.
Every accepted rule must result in a versioned artifact in this repository, not
just a conversation.

Typical deliverables:

- context, problem and proposed decision;
- affected users and journey;
- business rule and boundary examples;
- consulted areas and approvers;
- acceptance criteria and expected evidence;
- non-technical text and corresponding document.

## Codex

Use to turn accepted artifacts into contracts, migrations, endpoints, screens,
tests, security, CI, integrations and ADRs. Work in verifiable vertical slices and
preserve fail-closed behavior.

Before finishing a change, check:

- backend authorization and separation of duties;
- migration and versioning for persisted changes;
- audit event without sensitive content;
- happy-path, denial and conflict tests;
- documentation and contract updated;
- rollback or handling for an unavailable integration.

## Involvement of other areas

Security, Infra, DevOps, Architecture, Privacy, Legal, Compliance, Data and
Business are not "fixed" reviewers on every proposal. The policy engine determines
applicability and records the reason. Changing a trigger requires review by the
policy owner, examples, regression tests and a new policy version.

## Handoff format

```text
Objective and user
Current state and accepted decision
Rules and boundary cases
Required areas and evidence
Acceptance criteria
Impacted files/contracts
Risks and items explicitly out of scope
```

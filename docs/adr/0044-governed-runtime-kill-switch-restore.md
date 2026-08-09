# ADR 0044: Governed Runtime Kill-Switch Restore

- Status: Accepted
- Date: 2026-08-09
- Scope: P1.9d

## Context

P1.9a introduced immutable actuation requests, P1.9b independent human decisions, and P1.9c approved `engage_kill_switch` execution through Runtime Control. Restoration is a materially different risk decision: returning an Agent to an executable state can re-enable model routing and tool activity that containment intentionally stopped.

An approval to engage the kill switch must therefore never authorize restoration.

## Decision

Introduce a dedicated restore workflow with its own append-only evidence chain:

```text
P1.9c engage execution receipt
        ↓
restore request
        ↓
independent Security decision
        ↓
approved restore
        ↓
fresh TOCTOU validation
        ↓
RuntimeControlService.deactivate()
        ↓
restore execution receipt
```

The restore workflow is not represented as another value in the P1.9a actuation-request table. Separate tables and domain types make approval scope and audit interpretation explicit.

## Restore eligibility

A restore request may be created only when:

- the source P1.9c engage execution receipt is valid;
- the source Runtime Control transition is `APPLIED` and moved `inactive → active`;
- that source transition is still the latest authoritative transition for the Agent;
- the Agent still reports the kill switch as enabled and engaged;
- the linked Incident is `remediating` or `closed`;
- remediation owner, description, and due date are recorded;
- a closed Incident also has a resolution timestamp.

The remediation snapshot is committed into a canonical `remediation_digest` without persisting remediation text in the restore audit event.

## Stale remediation

Restore request idempotency uses:

```text
(source_execution_id, remediation_digest)
```

If remediation evidence changes after a request is created, the old request remains immutable but cannot be newly approved or executed. A new request may be created for the new remediation digest.

## Separation of Duties

Restore approval requires `ApprovalArea.SECURITY` and:

```text
decided_by != requested_by
```

Generic administrator status does not bypass Security approval or requester/approver separation.

Request and execution authority remain AI System owner or administrator responsibilities. Approval authority and execution authority are distinct.

## Approval scope isolation

The restore workflow has a distinct action:

```text
restore_kill_switch
```

It has independent:

```text
restore request digest
restore decision digest
restore execution digest
```

P1.9a/P1.9b/P1.9c `engage_kill_switch` request, decision, or execution evidence cannot be substituted for restore evidence.

The Runtime Control evidence reference is also namespaced separately:

```text
runtime-assurance-restore-decision:{decision_id}:{decision_digest}
```

## Execution boundary

Only the restore execution service may depend on Runtime Control. The request and decision services remain evidence-only.

The execution port exposes only:

```text
deactivate(...)
```

It does not expose `activate()` or a generic target-state command.

## Fresh TOCTOU validation

Immediately before a new Runtime Control restore transition, P1.9d revalidates:

- approved restore decision binding;
- current remediation digest;
- current Incident recovery state;
- current Agent version;
- kill-switch enabled/engaged state;
- latest Runtime Control transition;
- source engage execution authority.

If another Runtime Control transition superseded the source engagement, the restore fails closed rather than using stale approval.

## Partial-failure recovery

Runtime Control remains the single state-changing path. The restore decision digest is propagated in `evidence_reference`.

If Runtime Control commits a transition but receipt persistence subsequently fails, a retry searches for the transition using the same decision-bound evidence reference:

- `PENDING` transition: return dependency-unavailable/fail-closed and do not create another transition;
- `APPLIED` transition: validate the binding and reconstruct the immutable restore receipt;
- no transition: a new deactivation may be attempted only after fresh preconditions pass.

## Persistence

Migration `0019` adds:

- `runtime_assurance_restore_requests`;
- `runtime_assurance_restore_decisions`;
- `runtime_assurance_restore_executions`.

All three are append-only genesis/terminal receipt structures with version `1` constraints and canonical SHA-256 digests.

## Audit events

P1.9d emits content-minimized events:

```text
runtime_assurance.restore_requested
runtime_assurance.restore_approved
runtime_assurance.restore_rejected
runtime_assurance.restore_executed
runtime_assurance.restore_execution_recovered
```

Human decision reasons and remediation descriptions are not duplicated into the hash-chained audit payload.

## Non-goals

P1.9d does not add:

- automatic restoration;
- LLM-based recovery decisions;
- Policy Model Router calls;
- generic actuator configuration;
- client-selected target state;
- break-glass approval bypass;
- mutation of historical engage evidence;
- reuse of engage approval for restore.

## Consequences

The full containment/recovery chain becomes independently auditable:

```text
recommendation_digest
  ↓
engage request_digest
  ↓
engage decision_digest
  ↓
engage execution_digest
  ↓
remediation_digest
  ↓
restore request_digest
  ↓
restore decision_digest
  ↓
restore execution_digest
```

This introduces additional persistence and workflow steps, but makes the high-risk transition back to executable state explicit, reviewable, replay-safe, and cryptographically bound to both containment and remediation evidence.

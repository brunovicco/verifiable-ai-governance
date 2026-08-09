# ADR 0037 — Deterministic runtime assurance over sanitized telemetry

Status: Accepted  
Date: 2026-08-09

## Context

P1.7 made sanitized terminal runtime telemetry durable, authenticated, correlated and
tamper-evident. Governance can now prove that an Agent emitted a successful or failed terminal
event, but it still lacks a governed definition of what constitutes unhealthy runtime behavior.

The existing incident domain is intentionally human/control-plane governed. Allowing arbitrary
telemetry events to create incidents or engage a kill switch would collapse the separation between
operational signals and governance actions.

## Decision

P1.8a introduces a versioned `RuntimeAssurancePolicy` per governed Agent and an explicit,
deterministic evaluation command.

A policy may govern:

- bounded lookback window;
- bounded maximum terminal-event sample size;
- minimum evidence sample count;
- maximum failure/error rate;
- optional maximum p95 duration;
- optional maximum consecutive failures;
- severity to attach to a confirmed breach.

Only normalized terminal telemetry outcomes are eligible: `success`, `failure`, and `error`.
`started` events are not assurance evidence.

The evaluator is pure and does not invoke an LLM. It filters and orders the window deterministically,
computes the bounded metrics, emits `insufficient_data`, `healthy`, or `breached`, records controlled
breach reason codes, retains the exact source event IDs, and creates a canonical SHA-256 evidence
digest.

If a p95 threshold is configured, the duration sample count must independently satisfy
`minimum_samples`; otherwise the result is `insufficient_data`.

## Threshold semantics

- failure-rate breach: `observed_rate > max_failure_rate`;
- p95 breach: `observed_p95 > max_p95_duration_ms`;
- consecutive-failure breach:
  `observed_max_consecutive >= max_consecutive_failures`.

## Governance boundary

P1.8a does **not** automatically open/contain an incident, engage Runtime Control, issue or revoke
runtime authorization, accept free-form detection rules, or copy application/model content into
assurance evidence.

Policy changes and evaluations are owner/admin authorized and appended to the existing hash-chained
audit log.

## Persistence

P1.8a adds `runtime_assurance_policies` (one optimistic-versioned policy per Agent) and
`runtime_assurance_evaluations` (append-only evaluation evidence).

Evaluation audit payloads are minimized to policy version, outcome, controlled breach reasons,
severity and evidence digest. Detailed evidence retains at most 1000 source event IDs for exact
reconstruction.

## Follow-up

P1.8b may deterministically promote persisted breach evaluations into incident candidates and
deduplicate them against active incidents. P1.8c may produce governed response recommendations,
including whether Runtime Control should be considered. P1.8d will provide a live proof.

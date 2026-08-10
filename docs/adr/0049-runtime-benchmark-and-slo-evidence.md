# ADR 0049 — Runtime Benchmark and SLO Evidence

## Status

Accepted.

## Context

P2.0a binds the release source and evidence root, P2.0b binds software supply-chain security
evidence, and P2.0c binds deterministic build provenance plus GitHub/Sigstore attestations.
The release candidate still needs measurable runtime evidence showing that governance controls
remain operationally bounded.

A benchmark that calls a remote LLM would primarily measure provider/network variance rather than
the governance platform. A destructive load test would also be inappropriate for a release
evidence workflow.

## Decision

P2.0d records a sequential local reference benchmark for five existing runtime boundaries:

1. Governance readiness.
2. Governed model routing through the real Policy Model Router, before inference.
3. Runtime telemetry query.
4. Runtime Control state read through the existing P1.8/P1.9 state boundary.
5. Runtime Assurance evaluation.

The benchmark does not call an LLM and does not engage or restore the kill switch.

Raw evidence stores only sequence, elapsed milliseconds, success/failure and bounded HTTP status.
Response bodies, prompts, business payloads and credentials are not persisted.

The benchmark implementation commit may be newer than the P2.0a Governance source commit, but the
runner fails closed if any release-runtime path changed between them. Release tooling, tests,
documentation and evidence may differ without weakening runtime equivalence.

The policy in `config/release-runtime-slo-policy.json` is explicitly a local reference SLO profile,
not a production capacity claim. Observed rate is sequential completion rate, not maximum
throughput.

## Consequences

The release can provide p50/p95/p99 latency, error rate and sequential observed rate tied to exact
P2.0 release roots and the hardware/runtime class that produced the measurements.

Production SLOs still require environment-specific load, concurrency, traffic shape and capacity
engineering. P2.0d must not be cited as a production-scale throughput benchmark.

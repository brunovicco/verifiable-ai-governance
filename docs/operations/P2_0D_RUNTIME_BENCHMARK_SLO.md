# P2.0d — Runtime Benchmark & SLO Evidence

## Purpose

Generate content-addressed runtime benchmark evidence for `0.2.0-rc1` without remote LLM inference
or direct Runtime Control actuation.

## Preconditions

- Governance repository is clean and on the P2.0d implementation commit.
- Policy Model Router repository is clean and checked out exactly at the commit frozen by P2.0a.
- The local Governance API is ready at `http://127.0.0.1:8000`.
- Policy Model Router is ready at `http://127.0.0.1:8082`.
- The canonical demo seed exists.
- The canonical Agent is restored and its kill switch is inactive.
- Fresh runtime telemetry exists inside the Runtime Assurance lookback window.
- An enabled Runtime Assurance policy already exists.
- Run P1.9e immediately before P2.0d with `--report /tmp/p1.9-refresh.json` so the Git
  worktree remains clean while the telemetry window is refreshed and the Agent is restored.

## Benchmark semantics

The benchmark is sequential. It is intended to measure repeatable control-path latency, not
maximum system capacity.

Default measured samples:

- 50 readiness requests;
- 50 governed routing requests;
- 50 telemetry queries;
- 50 Runtime Control state reads;
- 20 Runtime Assurance evaluations.

Five warm-up operations are excluded from percentile calculations. The 50-routing default plus
five routing warm-ups remains below the Router's default 60-request window when the benchmark
starts from a fresh Router rate-limit window. For repeatable evidence, restart the local Router
before the benchmark or explicitly configure a higher benchmark-only rate limit.

Runtime Assurance evaluations create immutable evaluation evidence. They do not promote incidents
and do not perform automatic actuation.

## Run

```bash
uv run python -m scripts.run_release_runtime_benchmark \
  --policy-model-router-repo ../policy-model-router
```

A successful SLO result exits `0`. A valid benchmark whose reference SLO verdict is `fail` exits
`2`, preserving the evidence while preventing accidental release acceptance.

Generated files:

```text
artifacts/release/benchmark/runtime-benchmark-raw.json
artifacts/release/benchmark/runtime-benchmark-bundle.json
```

## Verify

```bash
uv run python -m scripts.verify_release_runtime_benchmark
```

The verifier does not rerun the live benchmark. It verifies:

- P2.0a release manifest binding;
- P2.0b security bundle binding;
- P2.0c build provenance binding;
- benchmark implementation commit;
- runtime-equivalence boundary;
- raw evidence SHA-256 and size;
- deterministic percentiles and summaries;
- SLO policy digest;
- per-scenario verdicts;
- aggregate bundle digest.

## Evidence commit pattern

Commit implementation first:

```bash
git commit -m "feat: add runtime benchmark and SLO evidence"
```

Run the live benchmark after that commit, verify it, then commit only the generated evidence:

```bash
git add artifacts/release/benchmark
git commit -m "docs: record v0.2.0-rc1 runtime benchmark evidence"
```

Do not regenerate P2.0a, P2.0b or P2.0c evidence during P2.0d.

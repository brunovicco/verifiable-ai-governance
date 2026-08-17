# GI-1 governed knowledge foundation

- **Status:** Current
- **Owner:** Platform engineering and architecture
- **Last reviewed:** 2026-08-17
- **Review trigger:** Knowledge authorization, resolution, integrity, limits or consumer changes
- **Authoritative sources:** ADR 0057 and the application-layer source gate

GI-1 provides the deterministic boundary that must run before a Governance Intelligence adapter
can consume source content. It does not connect a model, retrieval engine, vector database or
external knowledge provider.

GI-1A adds the first concrete adapter for clean, trusted uploaded evidence while preserving this
gate. It still adds no HTTP, retrieval or model consumer. See ADR 0058 and the GI-1A runbook.

## Guaranteed sequence

```text
reference validation
  → authorization for actor + governed subject + exact reference
  → exact artifact/version resolution
  → bounded read and SHA-256 verification
  → complete verified source set
  → future adapter consumption
```

`GovernanceIntelligencePort` accepts only `VerifiedGovernanceKnowledgeSource`. A raw
`GovernanceSourceReference` is not a valid analysis input.

## Verify locally

Run the focused application and boundary tests:

```bash
uv run pytest -q \
  apps/api/tests/test_governance_knowledge_application.py \
  apps/api/tests/test_architecture.py
```

Run the complete repository gate before merging:

```bash
uv run python scripts/quality_gate.py
```

## Composition requirements

A future composition root must supply positive, reviewed limits for:

- maximum references per request;
- maximum bytes for one source;
- maximum aggregate bytes for the complete request.

It must also provide:

- an authorizer that applies the authenticated actor and governed-subject access policy to the exact
  artifact, version, node/section and digest reference;
- a resolver that returns only the requested artifact identity and version through the bounded-read
  stream contract;
- adapter-level timeouts, cancellation and dependency error mapping;
- content handling controls appropriate to the selected source system.

The adapter review must test timeout and cancellation behavior, including stream cleanup. It must
also assess timing and transport side channels because identical failure payloads alone cannot
guarantee that a remote caller cannot distinguish denial from absence.

Do not bind an adapter that authorizes by artifact ID alone while ignoring subject, version or
reference scope.

## Failure behavior

| Failure | Result |
|---|---|
| denied or absent source | identical `source_unavailable` response; resolver is not invoked after denial |
| resolved identity/version mismatch | source is closed and the complete request fails |
| empty content or SHA-256 mismatch | no source set is released |
| per-source, aggregate or reference-count limit exceeded | request fails without a partial tuple |
| authorization/resolution/read/close dependency outage | content-free `dependency_unavailable` failure |
| duplicate reference or conflicting digest | request fails before any port call |

Failures must not include source bytes, document excerpts, artifact IDs or digests. Never log the
verified wrapper's content through custom serialization.

## Adding a concrete source adapter

Before connecting a source system:

1. document its authoritative identity and immutable version semantics;
2. define actor and governed-subject authorization, including denial behavior;
3. map unavailable and dependency failures without source enumeration;
4. prove that the resolver cannot substitute another artifact or version;
5. set size, timeout and media-type policies;
6. test actual-byte digest mismatches and stream cleanup;
7. document content sensitivity, retention, egress and logging controls;
8. run the architecture and repository quality gates.

Provider metadata, retrieved ranking and model interpretations do not replace application SHA-256
verification.

## Scope boundary

GI-1 introduces no endpoint, database table, migration, persistence for resolved bytes, retrieval,
index, embedding, prompt, model call, agent runtime or governed decision. Digest verification binds
bytes to a reference; it does not turn knowledge into evidence or an interpretation into authority.

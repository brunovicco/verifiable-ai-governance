# ADR 0051 - Deterministic canonical demo identities

## Status

Accepted.

## Date

2026-08-10.

## Context

ADR 0026 introduced the canonical, idempotent demo scenario. It deliberately kept
application-service-generated identifiers and therefore guaranteed stability only
while the seeded rows remained in the database. An explicit reset or a new empty
database produced new initiative, system, model, agent, assessment, approval,
evidence, and review-submission identifiers.

That behavior is insufficient for release evidence. URLs, screenshots, manifests,
runbooks, cross-repository integrations, and automated demonstrations need the
same semantic entity to have the same identifier when the canonical scenario is
rebuilt from an empty database.

The runtime routing decisions and incident already use UUIDv5 identifiers. The
remaining canonical business rows still depended on UUIDv4 defaults owned by the
normal persistence models.

## Decision

The canonical demo now separates a pure deterministic identity contract in
`scripts/canonical_demo_contract.py` from the SQLAlchemy assignment hook in
`scripts/canonical_demo_identity.py`.

- Use UUIDv5 with the existing fixed demo namespace.
- Derive IDs from the stable scenario ID plus a semantic identity key.
- Do not include `SCENARIO_VERSION` in identity derivation. Version changes modify
  the state of the same canonical business object rather than creating a new
  identity.
- Pin stable IDs for the canonical initiative, AI system, approved model,
  out-of-scope model, agent, assessments, review submissions, approval gates, and
  evidence rows.
- Preserve the already deterministic routing-decision and incident ID behavior.
- Keep the `scripts` package initializer side-effect free. The supported canonical
  seed CLI explicitly installs the SQLAlchemy `before_flush` listener before seed
  operations, and the seed regression suite installs the same hook explicitly.
- Keep the pure UUIDv5 contract importable by release tooling without importing
  SQLAlchemy or application persistence models.
- Match exact canonical markers and parent IDs before replacing a generated ID.
  Non-demo persistence keeps the existing UUIDv4 behavior.
- Keep the normal application services as the creation path. The demo identity
  layer changes persistence identity, not business validation, authorization,
  policy evaluation, review workflow, or audit behavior.
- Fail closed on partial canonical state exactly as before.

This decision supersedes only the generated-ID portion of ADR 0026. ADR 0026
remains authoritative for the canonical scenario, reset safeguards, and
application-service-driven seed workflow.

## Why UUIDv5

UUIDv5 gives a portable 36-character identifier compatible with the existing
schema while deriving the same value from the same semantic name. It requires no
central counter, database sequence, persisted lookup table, random seed, or
installation-specific state.

The semantic-key contract is intentionally small and human-auditable. Changing the
namespace, scenario ID, or identity key is treated as an explicit breaking change
to canonical demo identities.

## Alternatives considered

### Keep generated UUIDv4 values in the manifest

Rejected. A manifest created on one installation could not safely anchor URLs or
release evidence created on another installation.

### Add demo-specific ID parameters to production services

Rejected. The requirement belongs to the canonical seed and should not enlarge
production service contracts or expose client-selected entity identifiers.

### Insert canonical rows directly with SQLAlchemy

Rejected. It would bypass the application services that the canonical demo is
intended to exercise.

### Seed a pseudo-random UUID generator

Rejected. Call-order changes could silently change unrelated identities and would
make the mapping between a business entity and its ID implicit.

## Consequences

- Reset plus reseed preserves canonical business identifiers.
- Two clean databases derive the same canonical identifiers.
- The stable initiative and system IDs can anchor release evidence and URLs.
- Existing databases containing the complete canonical scenario are still valid;
  no migration or destructive rewrite is performed automatically.
- A database seeded before this ADR retains its old generated IDs until an
  explicitly authorized demo reset/reseed is performed.
- P2.0e.3 may rebuild release evidence against these stable identities without
  introducing another identity scheme.

## Security and privacy impact

The UUIDv5 names are synthetic scenario keys and contain no personal data,
credentials, prompts, model responses, or customer information. Predictability is
intentional for demo entities and must not be reused as a production identifier
strategy for security-sensitive resources.

## Validation

The canonical seed tests assert:

1. the fixed top-level UUID contract;
2. normal idempotent reruns preserve IDs;
3. a full guarded reset followed by reseed preserves every canonical business-row
   identity, including assessment, approval, evidence, and review-submission IDs;
4. partial canonical state continues to fail closed;
5. production reset remains prohibited.

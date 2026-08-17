# ADR 0056 - Governance Intelligence versioned contract evolution

- **Status:** Accepted
- **Date:** 2026-08-17
- **Decision owners:** Engineering, architecture and AI Governance

## Context

ADR 0054 established the advisory Governance Finding v1 trust boundary. ADR 0055 proved that the
current `governance-schemas` wheel can be consumed without source-tree or application coupling.
Neither decision defines how multiple wire versions coexist or prevents a model change from
silently overwriting the meaning of `schema_version="1.0"`.

The models are deliberately closed with `extra="forbid"`. That protects the authority boundary but
also means an older consumer is expected to reject a newer payload shape. Compatibility therefore
cannot mean that every old consumer reads every future payload. It needs an explicit direction,
version dispatch and lifecycle.

## Decision

### Separate package and wire versions

The Python package uses its own release version. Governance Finding uses an independent
`MAJOR.MINOR` wire version in `schema_version`. A package release may contain several supported wire
versions, and a package-only fix does not change the wire version.

The generic public parser requires `schema_version` to be present and a string. It dispatches only
through the immutable supported-version registry and fails closed with
`UnsupportedGovernanceFindingSchemaVersion` for absent or unknown values. Direct construction of a
specific model may retain Pydantic defaults for in-process ergonomics; wire ingestion must use the
generic parser.

### Immutable version artifacts

Every supported wire version has:

- a dedicated Pydantic envelope model;
- an immutable checked-in JSON Schema snapshot;
- at least one valid checked-in example;
- an entry in `compatibility-policy.json` with lifecycle status, model reference, schema digest,
  introduction package version and declared read compatibility.

The PH-2 verifier requires exact equality between the generated model schema and the snapshot and
verifies the snapshot SHA-256. An existing version snapshot must never be regenerated to hide a
wire change. A changed model requires a new wire version and new artifacts.

### Compatibility direction

The guaranteed direction is **backward reader compatibility** within one major:

```text
consumer supporting 1.1
  must still dispatch and validate 1.0 with the immutable 1.0 model
  and may also dispatch and validate 1.1 with the 1.1 model
```

Forward reader compatibility is not promised. A 1.0 consumer may reject a 1.1 payload. Producers
must emit a version accepted by the target consumer; version negotiation or transformation requires
an explicit adapter and is not inferred from payload shape.

The machine policy enforces that every minor version declares read compatibility with itself and
all earlier supported minors in the same major. Cross-major compatibility may be declared only
when it is explicitly implemented and tested.

### Change classification

| Change | Required action |
|---|---|
| Documentation, tests or implementation change with identical validation/wire semantics | Keep the wire version; normal package release rules apply |
| Add optional advisory data, extend a non-authoritative taxonomy or loosen a constraint without changing existing meaning | Add a new minor model/snapshot and keep all earlier minors readable |
| Remove/rename a field, add a required field, narrow accepted data, change field meaning or change structural interpretation | Add a new major model/snapshot and define explicit consumer migration |
| Add approval, authorization, compliance or another authority state | Forbidden by ADR 0054; a version bump does not authorize it |
| Change `trust_level="untrusted"` or `advisory_only=true` | Forbidden by ADR 0054; requires a different governed architecture, not contract evolution |

An enum addition belongs to a new minor only when it remains advisory and earlier version models
remain available. Reinterpreting an existing enum value is a semantic breaking change and requires
a new major.

### Lifecycle

Supported records use one of three statuses:

- `current`: the newest version produced by default; exactly one is required;
- `supported`: accepted without a deprecation signal;
- `deprecated`: still accepted while consumers migrate.

The compatibility manifest contains only readable versions. Removing a deprecated entry therefore
removes support and is a breaking release decision. It requires consumer evidence, release notes
and an explicit review; elapsed time alone does not retire a version.

### Gate behavior

The PH-2 gate validates the closed policy shape, ordered unique versions, lifecycle state,
backward-reader declarations, public registry/current version, snapshot digests/model equality and
all examples through both their specific model and public dispatch. It runs in the repository
quality gate and before the PH-1 cross-repository wheel probe.

Any mismatch fails the build. Errors contain bounded contract metadata, never finding statements,
source content, prompts or model responses.

## Consequences

### Positive

- `1.0` cannot drift silently after external adoption;
- consumers get deterministic fail-closed dispatch rather than shape guessing;
- several versions can coexist without weakening closed models;
- compatibility direction and lifecycle become machine-verifiable;
- package releases and wire evolution no longer share an ambiguous version number.

### Costs

- compatible evolution duplicates the prior model instead of editing it in place;
- every new wire version needs a schema snapshot, example, manifest record and cross-repository
  evidence;
- producers cannot assume older consumers accept newer minor payloads;
- version retirement requires explicit coordination.

## Rejected alternatives

### Treat package SemVer as the wire version

Rejected. One package may need to read several wire versions, and package-only fixes should not
change payload identity.

### Let Pydantic infer the version from payload shape

Rejected. Ambiguous parsing can assign the wrong semantics and makes downgrade behavior implicit.

### Make models permissive for forward compatibility

Rejected. Ignoring unknown fields would weaken the closed advisory boundary and could hide future
authority or sensitive-content fields.

### Overwrite the v1.0 snapshot after a model change

Rejected. Existing consumers identify semantics by `schema_version`; changing those semantics in
place breaks auditability and reproducibility.

### Add automatic cross-version transformation now

Rejected. Transformation rules are version-specific adapters and should be added only with an
actual new version and explicit semantic tests.

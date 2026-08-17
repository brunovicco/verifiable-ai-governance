# ADR 0055 - Governance Intelligence cross-repository compatibility gate

- **Status:** Accepted
- **Date:** 2026-08-16
- **Decision owners:** Engineering, architecture and AI Governance

## Context

ADR 0054 established Governance Finding v1 as a closed, advisory and non-authoritative contract in
the shared `governance-schemas` package. The intended consumers include this platform and external
repositories such as Policy Model Router and Credit Desk.

Source-level unit tests are necessary but insufficient for that boundary. They can pass while the
built package omits a module, its public exports drift, packaging introduces an application or
provider dependency, or a consumer succeeds only because the Governance source tree is on
`sys.path`.

PH-1 must prove that the distributable artifact remains portable before an external consumer relies
on it. It must not create a shared application port, edit consumer-owned code or define contract
evolution policy reserved for PH-2.

## Decision

### Artifact-first verification

The compatibility gate builds the actual `governance-schemas` wheel with the repository's declared
build backend. It inspects the wheel rather than importing the workspace package and requires:

- the public package and Governance Intelligence module;
- package metadata named `governance-schemas`, with Python `>=3.12`;
- Pydantic as the only runtime dependency;
- no packaged `ai_governance_api` application files;
- no imports of application, model-provider or agent-framework packages protected by ADR 0054.

The gate installs that wheel with `--no-deps` into an ephemeral target. Pydantic comes from the
already locked Governance environment, while `governance_schemas` must resolve from the ephemeral
installation. This avoids network-dependent resolution during a local gate and prevents an
editable workspace package from satisfying the probe accidentally.

### Consumer-owned execution context

The same probe runs with Python isolated mode (`-I`) and each consumer repository as its working
directory. The consumer source is not modified, installed or imported. Its checkout supplies an
independent execution context and a revision that is reported with the result.

The probe verifies the public exports and checked-in Governance Finding v1 fixture. It also applies
negative mutations to prove that authority fields, trusted status, non-advisory status and
out-of-range confidence remain rejected. Content-dump fields remain absent from the public models.

When external repositories are not supplied, the normal local quality gate uses an empty ephemeral
consumer. A dedicated GitHub Actions workflow checks out the current Policy Model Router and Credit
Desk default branches, runs the same probe on contract-related changes and runs weekly to detect
consumer drift.

### Failure semantics

Any build, metadata, dependency, import-origin, public-export, fixture or negative-boundary failure
returns a non-zero status. A failure blocks the applicable quality/CI gate. The verifier emits only
package metadata, repository revision and bounded errors; it does not execute consumer services or
read business data.

### Explicit PH-1 boundary

PH-1 verifies one current artifact and the current v1 behavioral invariants. It does not define
backward/forward compatibility, deprecation windows, supported version matrices or schema migration
rules. Those contract evolution decisions remain PH-2.

## Consequences

### Positive

- packaging regressions are caught before consumers depend on a broken artifact;
- the proof is independent of editable installs and the Governance working directory;
- provider/framework and application coupling are checked in the shipped artifact;
- weekly verification detects drift in the current external consumer checkouts;
- consumer repositories remain autonomous and require no PH-1 source changes.

### Costs

- the gate builds a wheel and starts isolated processes, adding a small amount of CI time;
- intentional runtime-dependency or Python-boundary changes require an explicit gate update;
- compatibility is behavioral for the checked-in v1 fixture, not a complete version-evolution
  policy.

## Rejected alternatives

### Import the editable workspace package

Rejected. It would not detect missing wheel files, incorrect metadata or source-tree leakage.

### Add Governance as an editable dependency in every consumer

Rejected. This would couple repository development environments and still would not verify the
published artifact shape.

### Execute consumer services in PH-1

Rejected. Service interoperability belongs to the existing cross-repository runtime E2E paths.
The finding contract has no runtime integration or authority behavior to exercise.

### Define a version matrix now

Rejected. Cross-version compatibility and evolution rules require the explicit PH-2 decision.

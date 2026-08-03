# Documentation governance

- **Status:** Current process
- **Owner:** Project maintainer
- **Last reviewed:** 2026-08-03
- **Review trigger:** Documentation structure or release process change

## Objective

Documentation is part of the assurance surface. A project that promises versioned,
verifiable governance should avoid unsupported claims and stale descriptions.

## Required metadata

Substantial documents should declare:

- status;
- owner role;
- last reviewed date;
- review trigger;
- authoritative code, policy, ADR or external references.

## Authority hierarchy

When sources disagree, use this order:

1. implemented and tested behavior;
2. accepted ADRs;
3. versioned schemas and policy catalogs;
4. architecture and operational documentation;
5. product overview and README;
6. roadmap and backlog.

A roadmap item must not be described as implemented because a data model or placeholder
exists.

## Status definitions

- **Draft:** under review and not authoritative;
- **Current:** reviewed against the current implementation;
- **Superseded:** retained for history and linked to its replacement;
- **Archived:** no longer part of the supported product direction.

## Change requirements

A pull request that changes governed behavior should update:

- relevant README capability statement;
- capability matrix status;
- architecture narrative;
- ADR when the decision is material;
- security/threat model when a boundary or privileged action changes;
- demo guide when the visible workflow changes;
- operational runbook when failure or recovery behavior changes.

## Claim rules

Use precise language:

- “implemented” only for an end-to-end supported path;
- “validated locally” when not tested in a real enterprise environment;
- “supports” or “contributes evidence to” for standards mappings;
- “tamper-evident” rather than “immutable” when only a hash chain protects history;
- “production-oriented reference implementation” rather than “production-ready” without
  environment evidence.

Avoid:

- “fully compliant”;
- “secure by default” without scope;
- “zero trust” as a generic label;
- test counts that are not generated automatically;
- availability, performance or recovery targets that have not been measured and approved.

## Review cadence

- README and capability matrix: every material feature change;
- security model and threat model: every trust-boundary change and at least quarterly;
- standards crosswalk: at least every six months or on reference revision;
- production readiness and runbooks: every deployment-architecture change and exercise;
- roadmap: quarterly.

## Automated checks to consider

- broken relative links;
- Mermaid syntax rendering;
- required metadata headers;
- stale date warning;
- references to nonexistent files;
- capability names not present in the matrix;
- catalog/version references generated from source;
- documentation update requirement for selected code paths.

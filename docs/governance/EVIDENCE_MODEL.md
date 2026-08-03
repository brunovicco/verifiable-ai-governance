# Evidence model

- **Status:** Current
- **Owner:** AI Governance and assurance
- **Last reviewed:** 2026-08-03
- **Review trigger:** Evidence type, storage, export, retention or audit change

## Purpose

Evidence supports a governance assertion. It does not automatically prove that a control
is effective, that a decision is legally sufficient or that an organization is
compliant.

The platform should preserve enough context to answer:

- what assertion or decision the evidence supports;
- which version and scope it relates to;
- who provided and reviewed it;
- when it was collected and reviewed;
- whether its integrity can be checked;
- where the authoritative content is stored;
- what limitations or expiry apply.

## Evidence classes

### Verified uploaded artifact

A file processed by the platform's evidence pipeline:

- allowed type and size;
- signature validation;
- SHA-256 digest;
- malware scan;
- application-generated private object key;
- persisted metadata and audit reference.

“Verified” refers to transport and integrity controls performed by the platform. It does
not mean that the file's claims are true.

### External reference

A URI, ticket, report identifier or other reference provided during a decision. It may
be useful provenance but has not passed the platform's file-verification pipeline.

External references must not be displayed as equivalent to verified uploaded artifacts.

### Derived system evidence

Evidence calculated by the platform from governed state, for example:

- policy version and risk breakdown;
- applicable control report;
- approval status;
- canonical scope digest;
- review validity;
- routing decision outcome;
- audit-chain verification result.

### Imported operational evidence

Future runtime, CI/CD, evaluation or monitoring evidence. Import adapters must define:

- source identity and trust level;
- schema and version;
- replay and idempotency behavior;
- content minimization;
- signature or integrity verification where available;
- mapping to governed assets and approved scope.

## Evidence lifecycle

```text
Requested → Collected → Validated → Linked → Reviewed
          → Accepted or Rejected → Retained → Superseded or Disposed
```

An artifact can remain historically valid for an old decision while being superseded for
the current scope. Supersession should not delete the prior decision record.

## Minimum metadata

| Field | Purpose |
|---|---|
| Evidence ID | Stable reference |
| Kind | Test, assessment, approval, architecture, security, operational or other category |
| Subject | Initiative, system, model, agent, control, review round or incident |
| Subject version/digest | Binds evidence to reviewed scope |
| Source type | Uploaded artifact, external reference, derived or imported |
| Provider identity | Person, service or system that supplied it |
| Collected at | Time of collection |
| Reviewed at | Time of assurance decision |
| Reviewer | Independent reviewer where required |
| Integrity digest | SHA-256 or stronger scheme where appropriate |
| Storage reference | Internal private location or external reference |
| Retention class | Policy for preservation and disposal |
| Sensitivity | Access and handling requirement |
| Expiry/review date | When evidence must be refreshed |
| Limitations | Known gaps, assumptions and scope exclusions |

## Binding evidence to decisions

A decision should reference evidence through stable IDs and should also capture:

- decision type and outcome;
- reviewer identity and authorization provenance;
- policy/control version;
- relevant entity version;
- canonical scope digest where applicable;
- timestamp and justification;
- limitations and expiry.

Changing an evidence file or reference after a decision must not silently change what the
decision relied on. A replacement becomes a new evidence item or a new version linked to
a new review.

## Integrity versus truth

The model distinguishes:

- **integrity:** the artifact can be shown to match the bytes originally stored;
- **authenticity:** the source identity is known or attested;
- **validity:** the evidence is appropriate for the assertion;
- **effectiveness:** the supported control achieves its objective;
- **compliance:** organizational and legal requirements are satisfied.

A SHA-256 digest supports integrity. It does not establish authenticity, validity,
effectiveness or compliance by itself.

## Access and minimization

- do not copy evidence content into logs or general audit events;
- expose evidence only to authorized participants, reviewers and administrators with a
  defined need;
- keep internal storage coordinates private;
- classify and protect backup packages as sensitive;
- define retention, deletion and legal-hold requirements outside local use;
- avoid collecting prompts, responses or personal data when metadata is sufficient.

## Evidence quality criteria

Reviewers should assess whether evidence is:

1. relevant to the control objective;
2. bound to the correct system and version;
3. complete for the claimed scope;
4. produced by an appropriate source;
5. recent enough for the risk and review frequency;
6. reproducible or independently verifiable where possible;
7. clear about failures, exclusions and assumptions.

## Future export package

A portable audit package should contain:

- versioned manifest;
- initiative and asset identifiers;
- policy and control versions;
- review rounds and decisions;
- evidence metadata and permitted content;
- object checksums;
- audit-chain checkpoint and verification instructions;
- explicit redactions and unavailable items.

Export must preserve access control and must not convert an internal evidence package
into a public artifact.

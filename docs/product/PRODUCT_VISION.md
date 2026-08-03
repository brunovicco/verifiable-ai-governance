# Product vision

## Problem

AI initiatives usually start out as disconnected documents, spreadsheets and
conversations. That makes it hard to know who is accountable for the solution,
which data and vendors are involved, where processing happens, which areas need to
approve it, and whether the system keeps operating within the approved
conditions.

## Vision

Offer a governance workspace that is understandable for business areas and
verifiable by technical and assurance teams. Every initiative must maintain an
explicit chain:

```text
Context → Risk → Controls → Approvals → Evidence → Operation → Review
```

## Audiences

- requesters and Product Owners who describe the purpose and are accountable for
  the initiative;
- AI Governance, which maintains taxonomies, controls, exceptions and the
  portfolio;
- Security, Architecture, Infra, DevOps and Data, who validate technical risks;
- Privacy, Legal and Compliance, who validate obligations and impacts;
- Operations and Model Owners, who track models and agents in production;
- audit and committees, who verify decisions and evidence without altering
  records.

## Value proposition

1. A guided form in non-technical language.
2. Explainable classification, never a risk "black box."
3. Conditional approvals, avoiding uniform bureaucracy and control gaps.
4. Evidence linked to the decision and an immutable event history.
5. Groundwork for monitoring runtime usage, changes, violations and incidents.

## Scope of version 0.1

- initiative registration and inventory;
- deterministic preliminary assessment;
- multidisciplinary approval workflow;
- documents required by context;
- separation of duties and audit trail;
- data models for the full technical inventory;
- demonstration portal and local execution.

## Out of scope for version 0.1

- automated legal opinions;
- ISO certification or automatic conformance declaration;
- orchestration of an official regulatory process;
- executing models or agents;
- production telemetry collection;
- digital signature or external document storage.

## MVP success measures

- a complete proposal is registered in under ten minutes;
- 100% of submitted proposals have owner, risk, policy version and gates
  recorded;
- no owner can approve their own initiative;
- no initiative is approved with a required gate pending or rejected;
- every decision has a justification, referenced evidence and an audit event;
- a concurrent change with a stale version is rejected.

## Corporate identity direction

The first planned corporate adapter will use Microsoft Entra ID for login and
Microsoft Graph to automatically identify the user's profile, department and
group memberships. Approval capability will continue to be governed by a
versioned catalog of App Roles/object IDs for areas, preserving least privilege
and the domain's independence from the vendor.

The design, phases and acceptance criteria are in
`docs/architecture/MICROSOFT_ENTRA_GRAPH_PLAN.md`.

# Incident response

- **Status:** Reference process
- **Owner:** Security operations and AI Governance
- **Last reviewed:** 2026-08-03
- **Review trigger:** Incident, exercise, severity-policy or response-control change

## Scope

This process covers incidents involving:

- unauthorized access or approval;
- evidence or audit integrity;
- model or agent use outside approved scope;
- unsafe or prohibited runtime action;
- identity, authorization or directory failure;
- compromised dependency or credential;
- privacy or data-residency concern;
- material control failure;
- backup, restore or availability failure.

## Severity model

| Severity | Description | Example |
|---|---|---|
| SEV-1 Critical | Active material harm, broad compromise or inability to contain | Unauthorized high-impact agent action, widespread evidence disclosure |
| SEV-2 High | Significant policy/security failure with limited scope or strong potential impact | Approval bypass, compromised privileged identity, invalid runtime routing |
| SEV-3 Medium | Contained failure requiring correction | Overdue remediation, failed scanner with uploads safely blocked |
| SEV-4 Low | Minor issue or near miss | Documentation mismatch, non-sensitive operational error |

Organizational incident policy may supersede these levels.

## Response lifecycle

```text
Detect → Triage → Contain → Preserve evidence → Investigate
       → Remediate → Validate → Restore → Reassess governance → Learn
```

## Immediate actions

1. assign an incident commander;
2. record detection time, reporter and affected assets;
3. classify severity and data sensitivity;
4. preserve relevant audit, routing, identity and infrastructure evidence;
5. contain using the narrowest effective control;
6. escalate to security, privacy, legal, compliance or business owners as required.

## Containment controls

Available or expected controls include:

- block a platform identity;
- activate system or agent kill switch;
- suspend or retire an affected asset;
- revoke App Role/group membership at the identity provider;
- revoke provider sessions and credentials;
- disable model-router or external integration access;
- restrict object-storage or database credentials;
- block evidence uploads when scanning or storage integrity is uncertain;
- create a temporary exception only when it reduces total risk and has independent approval.

Platform identity restriction does not replace provider-side revocation.

## Evidence preservation

Preserve:

- incident record and timeline;
- affected entity IDs, versions and scope digests;
- policy and authorization-catalog versions;
- review rounds and approval provenance;
- routing attempts and blocked reasons;
- relevant audit-chain range and verification result;
- sanitized logs and traces;
- evidence checksums and access logs;
- deployment, migration and image versions;
- backup state when compromise time is uncertain.

Do not indiscriminately copy prompts, documents or personal data. Preserve only what is
necessary and protect the incident package according to its sensitivity.

## Investigation questions

- What governance assertion or control failed?
- Was the identity authentic and correctly authorized?
- Did approved scope change before or during the event?
- Was an external dependency trusted beyond its intended authority?
- Did a fail-closed control behave as designed?
- Which evidence and decisions may be unreliable?
- Are related systems, models or agents affected?
- Does the event invalidate an approval or assessment?
- Are regulatory, contractual or affected-person notifications required?

## Remediation

A remediation plan should contain:

- root and contributing causes;
- corrective and preventive actions;
- owner and due date;
- validation evidence;
- affected policies, catalogs, code and runbooks;
- reassessment requirements;
- criteria for removing containment;
- residual risk and exception status.

## Restoration

Restore only after:

- the exploited path is removed or acceptably controlled;
- identity and credentials are rotated or validated;
- affected data and evidence integrity are assessed;
- necessary approvals are repeated;
- monitoring is active;
- rollback or kill-switch reactivation remains available;
- the incident commander and accountable owner approve restoration.

Do not automatically reuse approval that was made under invalidated assumptions.

## Post-incident review

Within the organizational target period, document:

- concise impact statement;
- timeline;
- detection effectiveness;
- control successes and failures;
- root cause and contributing conditions;
- lessons for policy, architecture and operations;
- required test, threat-model and documentation updates;
- portfolio search for similar exposure.

## Exercises

Run recurring exercises for:

1. compromised reviewer identity;
2. external router returning an unauthorized group;
3. malicious evidence upload;
4. ClamAV outage;
5. stale Entra authorization;
6. audit-integrity alert;
7. agent operating outside approved scope;
8. database restore after a simulated incident.

# Governance model

## Positioning

This project translates governance principles and requirements into an operational
model of risks, controls, stage gates, decisions and evidence. It complements
applicable frameworks and obligations; it does not replace them or automatically
declare compliance.

## Five layers

1. **Organizational governance:** principles, accountability, committees, exceptions
   and RACI.
2. **Risk and impact:** inventory, taxonomy, affected people, data, autonomy, scale,
   reversibility and dependency.
3. **Lifecycle:** intake, assessment, approval, build, validation, production,
   monitoring, change and retirement.
4. **Technical controls:** models, data, RAG, agents, tools, MCP, security,
   observability and evaluations.
5. **Evidence and assurance:** tests, approvals, provenance, audit, reviews, incidents
   and compensating controls.

## Principles

- identifiable human accountability;
- legitimate purpose, necessity and proportionality;
- security and privacy by design;
- transparency appropriate to the affected people;
- effective human oversight, with authority and time to intervene;
- contestability and remediation when there is material impact;
- least privilege for models, agents, tools and integrations;
- automatic corporate identity with authorization derived from explicit, versioned
  and auditable directory mappings;
- versioned, explainable decisions backed by evidence;
- fail-closed promotion and safe rollback;
- monitoring proportional to risk throughout the lifecycle.

## Preliminary classification

The 0-100 score considers impact (30), data (25), autonomy (25), exposure (10) and
regulatory context (10). Escalation rules ensure that rights/safety and high autonomy
are not diluted by a low sum in other dimensions.

| Tier | Minimum treatment |
|---|---|
| Low | owner, system card, simple periodic review |
| Medium | applicable technical gates, tests and defined monitoring |
| High | independent assurance, threat model, monitoring and frequent reviews |
| Critical | committee decision, reinforced oversight, autonomy limits and stop criteria |

The score is triage, not a final decision. Reviewers can raise the risk with
justification; a future reduction will require evidence and AI Governance approval.

## Operational inventory

Only an approved initiative can give rise to an AI system. The initiative owner
assigns an identifiable responsible party to the system; that responsible party
controls the registration of models and agents. New models and agents start in
`draft`, since the initiative's approval does not replace the asset's own assessment,
approved scope or technical baseline.

Architecture approves model scope and Security approves agent scope, always with
segregation between owner and reviewer. The decision binds version, region, use cases,
data classes, baseline or autonomy limits to a canonical digest and a risk-proportional
review date. Material changes remove the approval; changes to models also invalidate
dependent agents. Agents can only be approved when all permitted models have a current
review. Historical lifecycle and validity are distinct dimensions: an asset can remain
`status=approved` while consumers must still require `review_state=current`.
Transitional migration markers do not constitute a valid version or region for
approval.

Physical deletion is not part of the normal flow. Retiring a system changes its
state, disables the production flag, retires linked assets and records auditable
evidence. Subsequent changes are blocked.

## Control chain

Each control must declare an identifier, objective, type, applicability, owner,
requirements, evidence, review frequency, implementation and limitations. The
complete catalog is a P0 backlog item following the scaffold.

```text
Identified risk
  → applicable control
    → gate and owner
      → versioned evidence
        → decision
          → monitoring and review
```

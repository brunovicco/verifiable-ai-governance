# Documentation index

This index organizes the project documentation by audience and decision type.

## Start here

| Audience | Recommended path |
|---|---|
| Recruiter or hiring manager | [Executive overview](executive/EXECUTIVE_OVERVIEW.md) → [Capability matrix](product/CAPABILITY_MATRIX.md) |
| CTO or platform leader | [Executive overview](executive/EXECUTIVE_OVERVIEW.md) → [Architecture](architecture/ARCHITECTURE.md) → [Production readiness](operations/PRODUCTION_READINESS.md) |
| AI Governance or GRC | [Governance model](governance/GOVERNANCE_MODEL.md) → [Evidence model](governance/EVIDENCE_MODEL.md) → [Control crosswalk](governance/CONTROL_CROSSWALK.md) |
| Security architect | [Security model](security/SECURITY_MODEL.md) → [Threat model](security/THREAT_MODEL.md) → [Trust boundaries](architecture/TRUST_BOUNDARIES.md) |
| Developer | [Demo guide](demo/DEMO_GUIDE.md) → [API guide](integrations/API_GUIDE.md) → [Architecture](architecture/ARCHITECTURE.md) |
| Operator or SRE | [Production readiness](operations/PRODUCTION_READINESS.md) → [Observability](operations/OBSERVABILITY.md) → [Incident response](operations/INCIDENT_RESPONSE.md) |

## Product and positioning

- [Executive overview](executive/EXECUTIVE_OVERVIEW.md)
- [Product vision](product/PRODUCT_VISION.md)
- [Capability matrix](product/CAPABILITY_MATRIX.md)
- [Roadmap](product/ROADMAP.md)
- [MVP backlog](backlog/MVP_BACKLOG.md)
- [Demo guide](demo/DEMO_GUIDE.md)

## Governance and assurance

- [Governance model](governance/GOVERNANCE_MODEL.md)
- [Approval flow](governance/APPROVAL_FLOW.md)
- [Stage gates](governance/STAGE_GATES.md)
- [RACI](governance/RACI.md)
- [Control catalog](governance/CONTROL_CATALOG.md)
- [Evidence model](governance/EVIDENCE_MODEL.md)
- [Risk methodology](governance/RISK_METHODOLOGY.md)
- [Control crosswalk](governance/CONTROL_CROSSWALK.md)
- [International processing](governance/INTERNATIONAL_PROCESSING.md)
- [Monitoring principles](governance/MONITORING.md)

## Architecture and security

- [Architecture](architecture/ARCHITECTURE.md)
- [Trust boundaries](architecture/TRUST_BOUNDARIES.md)
- [Security model](security/SECURITY_MODEL.md)
- [Threat model](security/THREAT_MODEL.md)
- Architecture Decision Records: `architecture/adr/`

ADRs are authoritative for accepted engineering decisions. Narrative documents should
link to the relevant ADR instead of duplicating detailed rationale.

## Operations

- [Production readiness](operations/PRODUCTION_READINESS.md)
- [Observability](operations/OBSERVABILITY.md)
- [Incident response](operations/INCIDENT_RESPONSE.md)
- Existing service-specific runbooks remain under `operations/`.

## Integrations and deployment

- [API guide](integrations/API_GUIDE.md)
- [Policy model router](integrations/POLICY_MODEL_ROUTER.md)
- [Deployment options](deployment/DEPLOYMENT_OPTIONS.md)

## Project governance

- [Documentation governance](project/DOCUMENTATION_GOVERNANCE.md)
- [License decision](project/LICENSE_DECISION.md)
- Root [CONTRIBUTING.md](../CONTRIBUTING.md)
- Root [SECURITY.md](../SECURITY.md)

## Document status convention

Every substantial document should include:

```text
Status: Draft | Current | Superseded
Owner: role or maintainer
Last reviewed: YYYY-MM-DD
Review trigger: time-based or event-based
Authoritative sources: code, ADRs, policy version or external reference
```

A recent file modification timestamp is not evidence that the content is current.
Content must be reviewed against implemented behavior.

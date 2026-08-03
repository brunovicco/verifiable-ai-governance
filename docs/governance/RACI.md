# RACI

Legend: **R** executes, **A** is accountable for the outcome, **C** is consulted,
**I** is informed. A single process can have several technical responsibles, but only
one accountable business owner per initiative.

| Activity | Business | AI Gov. | Architecture | Security | Infra | DevOps | Privacy | Legal | Compliance | Data |
|---|---|---|---|---|---|---|---|---|---|---|
| Propose use case | A/R | C | I | I | I | I | I | I | I | C |
| Classify preliminary risk | C | A/R | C | C | I | I | C | C | C | C |
| Validate architecture | C | C | A/R | C | C | C | I | I | I | C |
| Threat model and security controls | I | C | C | A/R | C | C | C | I | C | I |
| Validate capacity, region and resilience | I | C | C | C | A/R | C | C | I | I | C |
| Validate delivery, rollback and observability | I | C | C | C | C | A/R | I | I | I | I |
| RIPD and personal data processing | C | C | I | C | I | I | A/R | C | C | C |
| Contractual basis and international transfer | I | C | I | C | C | I | R | A | C | I |
| Sector-specific obligations | C | C | I | C | I | I | C | C | A/R | I |
| Quality, lineage and data access | C | C | C | C | I | I | C | I | C | A/R |
| Accept residual risk and go-live | A | R | C | C | C | C | C | C | C | C |
| Monitor production | A | C | I | C | C | R | C | I | C | R |
| Manage incident | A | C | C | R | C | R | C | C | C | C |
| Audit evidence | I | R | I | I | I | I | I | I | C | I |

## Minimum segregation

- an owner/requester does not decide gates on their own initiative;
- whoever develops or operates does not solely issue the assurance verdict;
- high/critical risk requires independent people across approving areas;
- a platform administrator does not automatically receive approval authority;
- an exception is not approved by the same role that requests or implements it.

## Corporate identity

- IAM administers app registrations, consents, groups and lifecycle in Entra;
- Security approves trust boundaries, Conditional Access, credentials and scopes;
- AI Governance owns the App Role/group → approval area mapping;
- Privacy validates attributes collected from Graph, purpose, retention and location;
- Infra/DevOps operate configuration, secret manager, availability and observability;
- none of these functions can alter a mapping alone and approve using the capability
  it just granted itself.

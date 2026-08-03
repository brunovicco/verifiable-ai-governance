# Trust boundaries

- **Status:** Current
- **Owner:** Architecture and security
- **Last reviewed:** 2026-08-03
- **Review trigger:** Network, identity, storage, runtime or deployment topology change

## Context diagram

```mermaid
flowchart LR
  subgraph UserZone[User device]
    B[Browser]
  end

  subgraph AppZone[Application trust zone]
    W[Next.js portal]
    A[FastAPI API]
    P[Policy and domain rules]
  end

  subgraph DataZone[Governance data zone]
    DB[(PostgreSQL)]
    OS[(Private object storage)]
  end

  subgraph SecurityServices[Security services]
    AV[ClamAV]
    IDP[OIDC / Microsoft Entra ID]
    GR[Microsoft Graph]
  end

  subgraph ExternalPolicy[External policy service]
    MR[Policy model router]
  end

  subgraph FutureRuntime[AI runtime boundary]
    RT[Model and agent runtime]
    OT[Sanitized telemetry adapter]
  end

  B --> W
  B -->|Bearer token / local demo identity| A
  W --> A
  A --> P
  A --> DB
  A --> OS
  A --> AV
  A --> IDP
  A --> GR
  A -->|Minimized routing metadata| MR
  MR -->|Logical group or rejection| A
  A -. Governance decision .-> RT
  RT -. Sanitized evidence .-> OT
  OT -. Planned .-> A
```

## Boundary assumptions

### User device

The browser and local device are untrusted. Client-side hiding, validation or route
protection is a usability feature, not authorization.

### Application trust zone

The API process is trusted to execute reviewed code and configuration. The portal is not
trusted with governance authority. Domain and application rules remain authoritative.

### Governance data zone

PostgreSQL and object storage contain sensitive governance information. Network access,
credentials, encryption, retention and backup handling must be controlled independently
from application authorization.

### Identity and directory services

Identity providers attest authentication. They do not directly decide governance-area
semantics. The application maps trusted claims and directory object IDs through an
explicit, versioned catalog.

### Malware scanner

ClamAV is trusted to provide a scan result but is not treated as infallible. Scanner
unavailability blocks the upload. Allowed files can still require safe viewers and
content-disarm policies in stricter environments.

### External model router

The router is not trusted to approve governance scope. It may choose only among logical
groups that the application has already determined to be eligible. Its response is
validated before acceptance.

### AI runtime

A future or external runtime must enforce or consume governance decisions correctly. A
runtime that bypasses the governance API remains outside the assurance boundary.

## Data-flow rules

| Flow | Allowed data | Prohibited by default |
|---|---|---|
| Browser → API | Form fields, identifiers, expected versions, authorized files | Service credentials |
| API → Identity provider | Token verification/JWKS requests | Governance evidence content |
| API → Microsoft Graph | OBO token exchange and minimal profile/group queries | Assessment and evidence data |
| API → Model router | Workload, risk, data class, approved group constraints, cost/latency metadata | Prompts, documents, credentials, model responses |
| API → Logs | IDs, digests, categories, status, timing | Tokens, full assessment answers, evidence bodies, prompts and secrets |
| Runtime → Governance | Sanitized identifiers, metrics, decisions and evidence references | Raw content unless separately approved |

## Deployment implications

- terminate TLS at a controlled boundary and preserve authenticated identity to the API;
- place PostgreSQL and object storage on private networks;
- restrict ClamAV and router egress/ingress to required paths;
- use workload identity or secret management for service credentials;
- apply edge rate limiting and request-size limits;
- export security events to an independently controlled monitoring destination;
- separate local demonstration configuration from shared environments.

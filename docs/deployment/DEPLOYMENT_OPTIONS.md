# Deployment options

- **Status:** Reference architecture
- **Owner:** Platform architecture
- **Last reviewed:** 2026-08-03
- **Review trigger:** Supported infrastructure or operational requirement change

## Deployment principles

Regardless of platform:

- keep the API stateless between requests;
- treat PostgreSQL and object storage as managed backing services;
- run schema migration as an explicit blocking step;
- validate security configuration before serving traffic;
- use private networking for data services;
- store secrets outside images and source control;
- require server-side encryption for evidence outside local mode;
- maintain fail-closed behavior for identity, storage, scanning and routing dependencies;
- preserve audit and backup data outside ephemeral compute.

## Option 1 - Docker Compose

### Use case

- local development;
- demonstrations;
- functional testing;
- architecture evaluation.

### Components

- Next.js portal;
- FastAPI API;
- PostgreSQL;
- MinIO or compatible object storage;
- ClamAV;
- optional local OIDC provider.

### Limitations

Compose is not the default production recommendation for high availability, managed
secrets, rolling deployment, multi-zone resilience or operational separation.

## Option 2 - Kubernetes or OpenShift

### Suggested topology

```text
Ingress / API gateway
  ├── web deployment
  └── API deployment
        ├── managed PostgreSQL
        ├── private S3-compatible storage
        ├── ClamAV service or approved scanning service
        ├── OIDC / Entra ID
        └── external policy model router
```

### Required decisions

- migration Job and deployment ordering;
- readiness versus liveness probes;
- horizontal scaling and database pool limits;
- Pod security and non-root execution;
- network policies and egress allowlists;
- secret-manager integration;
- persistent audit/export strategy;
- scanner scaling and signature updates;
- disruption budgets and zone spread;
- backup orchestration and restore testing.

## Option 3 - Azure-oriented deployment

Possible managed services:

- Azure Container Apps, AKS or App Service for compute;
- Azure Database for PostgreSQL;
- Azure Blob Storage with private endpoints;
- Microsoft Entra ID;
- Microsoft Graph OBO;
- Key Vault and workload identity;
- Azure Monitor/OpenTelemetry export;
- approved malware-scanning architecture.

Important validation:

- tenant-specific authority and audience;
- Conditional Access;
- App Roles/group-object mappings;
- private DNS and endpoints;
- Blob encryption, immutability and retention when required;
- provider-side session and role revocation procedures.

## Option 4 - AWS-oriented deployment

Possible managed services:

- ECS/Fargate or EKS;
- Amazon RDS for PostgreSQL;
- Amazon S3 with bucket policies, KMS and private endpoints;
- external enterprise OIDC or federated identity;
- Secrets Manager and IAM roles for tasks/service accounts;
- CloudWatch/OpenTelemetry export;
- approved malware-scanning architecture.

Important validation:

- OIDC claim and role mapping;
- KMS key ownership and rotation;
- S3 block-public-access, retention and access logging;
- VPC endpoints and egress controls;
- container and dependency provenance.

## Option 5 - restricted or regulated environment

Additional considerations:

- private or disconnected container registry;
- mirrored and approved dependency sources;
- locally managed OIDC and object storage;
- controlled ClamAV signature distribution;
- no public network egress except explicitly approved dependencies;
- internal timestamping, SIEM or WORM audit destinations;
- deployment evidence, image digests and signed artifacts;
- stricter document rendering or content-disarm controls;
- formal data-residency and backup-location approvals.

## Multi-environment strategy

At minimum separate:

- local development;
- automated test;
- integration or staging;
- production.

Do not copy production evidence or identity data into lower environments without an
approved masking and data-handling process.

## Deployment artifact

Every deployment should record:

- application version/commit;
- container image digests;
- database migration revision;
- policy-control catalog version/digest;
- directory authorization catalog version/digest;
- environment and region;
- configuration change reference;
- approver and deployment identity;
- rollback or forward-fix plan.

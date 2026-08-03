# Production readiness

- **Status:** Checklist for an adopting organization
- **Owner:** Platform engineering, security and operations
- **Last reviewed:** 2026-08-03
- **Review trigger:** Deployment architecture, dependency or operational-policy change

The repository is a production-oriented reference implementation. Production readiness
is an environment-specific decision and requires evidence beyond successful local
execution.

## Readiness status legend

- `[ ]` not assessed;
- `[~]` partially addressed or requires organizational configuration;
- `[x]` evidenced for the target environment.

## Governance and ownership

- [ ] Service owner and technical owner are assigned.
- [ ] Data owner and security owner are assigned.
- [ ] Supported use cases and prohibited use cases are documented.
- [ ] Risk tier and business criticality are approved.
- [ ] RACI and on-call escalation paths are current.
- [ ] Exceptions have expiry and compensating controls.

## Identity and access

- [ ] Real Microsoft Entra/OIDC tenant validation is complete.
- [ ] Conditional Access behavior is tested.
- [ ] Tenant allowlist is configured.
- [ ] App Roles/object-ID authorization catalog is reviewed and versioned.
- [ ] Guest-account policy is validated.
- [ ] Group overage and Graph failure are tested.
- [ ] Provider-side role removal and session revocation runbooks exist.
- [ ] Emergency platform restriction is tested.
- [ ] Break-glass access is defined and audited.

## Secrets and cryptography

- [ ] No local demonstration secret is used outside local mode.
- [ ] Secrets come from a managed secret store or workload identity.
- [ ] Audit integrity material has rotation and access policy.
- [ ] Database and object-storage encryption is enabled.
- [ ] TLS is enforced at all external and sensitive internal boundaries.
- [ ] Certificate rotation is tested.

## Database and migrations

- [ ] Production database is private and access-restricted.
- [ ] Alembic migration runs as a controlled deployment step.
- [ ] API startup remains blocked on migration failure.
- [ ] Migration rollback or forward-fix policy is documented.
- [ ] Connection pool and timeout values are load-tested.
- [ ] Point-in-time recovery is configured where required.

## Evidence storage

- [ ] Bucket/container creation is controlled outside the application.
- [ ] Server-side encryption is required.
- [ ] Public access is blocked.
- [ ] Service credentials have minimum required permissions.
- [ ] Object retention, deletion and legal-hold policies are defined.
- [ ] Malware-scanner availability and signature update are monitored.
- [ ] Safe document-viewing requirements are defined.

## Backup and disaster recovery

- [ ] Recovery-point objective (RPO) is approved.
- [ ] Recovery-time objective (RTO) is approved.
- [ ] Write quiescence or a consistent snapshot strategy is defined.
- [ ] Backup packages are encrypted and access-controlled.
- [ ] Restore tests run on a schedule.
- [ ] Database revision, table counts and object checksums are verified.
- [ ] Cross-region or off-site storage is assessed.
- [ ] Disaster-recovery roles and communication are tested.

## Network and dependency controls

- [ ] API and portal ingress use controlled TLS endpoints.
- [ ] PostgreSQL, object storage and scanner are on private networks.
- [ ] Egress to identity, Graph and model router is restricted.
- [ ] DNS and certificate failure behavior is tested.
- [ ] Timeouts, retries and circuit behavior are explicit.
- [ ] External router cannot receive prompts or documents.
- [ ] Edge request-size and rate limits are configured.

## Application security

- [ ] Threat model is reviewed for the target deployment.
- [ ] Dependency, secret and container scanning are enabled.
- [ ] Base images and GitHub Actions are reviewed and pinned according to policy.
- [ ] Software bill of materials and provenance requirements are defined.
- [ ] Negative authorization tests run in CI.
- [ ] Security headers and CORS policy are validated.
- [ ] Vulnerability reporting channel is monitored.

## Observability

- [ ] Structured logs have correlation IDs.
- [ ] Tokens, prompts, responses and evidence content are excluded by default.
- [ ] Authentication, authorization and emergency restriction events are monitored.
- [ ] Migration, database, scanner, storage, Graph and router health are monitored.
- [ ] SLOs and alert thresholds are defined.
- [ ] Alerts route to accountable teams.
- [ ] Audit-chain verification runs on a schedule.

## Performance and capacity

- [ ] Representative portfolio and concurrency load tests exist.
- [ ] Upload throughput and scanner capacity are measured.
- [ ] Database indexes and slow queries are reviewed.
- [ ] Dashboard aggregation performance is tested at expected scale.
- [ ] Identity and Graph rate-limit behavior is validated.
- [ ] Resource limits and autoscaling strategy are defined.

## Privacy and data lifecycle

- [ ] Data inventory and processing purpose are approved.
- [ ] Retention and deletion rules exist for each entity and evidence class.
- [ ] International transfers and storage regions are reviewed.
- [ ] Access to assessments and evidence is need-to-know.
- [ ] Logs and backups follow the same classification requirements.
- [ ] Data-subject and legal-hold procedures are mapped where applicable.

## Incident readiness

- [ ] Severity model and incident owner are defined.
- [ ] Kill switch and identity block are exercised.
- [ ] Evidence preservation process is documented.
- [ ] External-provider escalation contacts are current.
- [ ] Regulatory and customer notification responsibilities are mapped.
- [ ] Post-incident reassessment and approval invalidation criteria are defined.

## Release gate

Production release should require a signed record containing:

- target version and image digests;
- migration revision;
- policy and authorization catalog versions/digests;
- completed readiness exceptions;
- test and security evidence;
- backup/restore status;
- deployment approvers and rollback owner.

# Security policy

## Reporting a vulnerability

Do not report suspected vulnerabilities through a public GitHub issue, discussion or
pull request.

Use GitHub private vulnerability reporting when it is enabled for this repository. If it
is not available, contact the repository owner through a private, authenticated channel
and request a secure reporting method before sharing exploit details or sensitive data.

Include:

- affected component and version or commit;
- impact and prerequisites;
- reproducible steps or a minimal proof of concept;
- whether sensitive data was accessed;
- suggested mitigation, when known;
- a safe contact method.

Do not include real credentials, production evidence, personal data or third-party
confidential information.

## Response process

The maintainer should:

1. acknowledge receipt through the private channel;
2. validate scope and severity;
3. coordinate containment and a fix;
4. preserve evidence without unnecessary sensitive content;
5. notify affected users when appropriate;
6. publish a security advisory after a fix or agreed disclosure date;
7. update the threat model and regression tests.

No guaranteed response time is currently offered. A formal service-level target should
be added only when a monitored security contact and maintenance commitment exist.

## Supported versions

Until tagged supported releases are defined, security fixes target the current default
branch. Older commits and forks are not supported.

## Security boundaries

This project is a reference implementation. Secure operation depends on environment
configuration, identity provider, network, database, object storage, malware scanner,
secret management and operating procedures.

Review:

- `docs/security/SECURITY_MODEL.md`;
- `docs/security/THREAT_MODEL.md`;
- `docs/operations/PRODUCTION_READINESS.md`.

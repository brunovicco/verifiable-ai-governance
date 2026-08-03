# Directory access incident response

## Purpose

Immediately stop an Entra identity's access to the platform, coordinate the
provider's actions, and restore access only after remediation. The local block
complements IAM actions; it does not replace disabling the account, removing group
membership or revoking sessions in Microsoft Entra ID.

## Prerequisites

- two controlled and monitored emergency administrative identities;
- `tenant_id` and `object_id` confirmed against a trusted IAM source;
- tenant present in `OIDC_ALLOWED_TENANT_IDS`;
- an incident or change with a traceable reference;
- operational access to Entra for the applicable external actions.

Never obtain the target solely from a name, email or text submitted by the
requester. Do not copy tokens, secrets, Graph responses or group inventories into
tickets and logs.

## 1. Block on the platform

Use an administrative identity different from the target:

```bash
curl --fail-with-body \
  --request POST "${GOVERNANCE_API_URL}/api/v1/auth/directory-access/block" \
  --header "Authorization: Bearer ${GOVERNANCE_ADMIN_TOKEN}" \
  --header "Content-Type: application/json" \
  --data '{
    "tenant_id": "11111111-1111-4111-8111-111111111111",
    "object_id": "22222222-2222-4222-8222-222222222222",
    "reason": "account_compromised",
    "reference": "INC-2026-184"
  }'
```

Accepted block reasons:

- `account_compromised`;
- `personnel_offboarding`;
- `incident_response`;
- `policy_violation`;
- `manual_emergency`.

Expected response: `blocked=true`, an opaque ID, timestamp and version. The
operation changes state, invalidates derived authorization and writes an audit
entry in the same transaction.

## 2. Confirm containment

1. run a protected request with a test session belonging to the target;
2. confirm `403` with `Directory identity access is suspended`;
3. confirm the `directory_access.blocked` event and its
   `authorization_cache_version` in the trail;
4. verify the payloads contain the target's digest, reason and reference, not the
   UUIDs themselves.

A database failure or inconsistent binding should produce `503`. Do not work around
this result or switch the service to fail-open during the incident.

## 3. Coordinate actions in Microsoft Entra ID

IAM determines and executes the appropriate actions, which may include:

- disabling the account to prevent new tokens;
- revoking sessions/refresh tokens;
- removing App Roles and group memberships;
- disabling or flagging compromised devices;
- revoking affected consents or credentials;
- applying or reviewing Conditional Access and Continuous Access Evaluation.

`revokeSignInSessions` requires a specific permission, can take a few minutes, and
does not revoke external users' sessions in the resource tenant. The platform's
session is controlled by this runbook's local block. Record evidence of the Entra
action without storing tokens or secrets.

## 4. Restore with current authorization

Only restore once IAM, Security and the incident owner confirm remediation.

```bash
curl --fail-with-body \
  --request POST "${GOVERNANCE_API_URL}/api/v1/auth/directory-access/restore" \
  --header "Authorization: Bearer ${GOVERNANCE_ADMIN_TOKEN}" \
  --header "Content-Type: application/json" \
  --data '{
    "tenant_id": "11111111-1111-4111-8111-111111111111",
    "object_id": "22222222-2222-4222-8222-222222222222",
    "reason": "remediation_completed",
    "reference": "INC-2026-184"
  }'
```

Accepted restore reasons: `remediation_completed`, `false_positive` and
`access_reinstated`. Restoring keeps the authorization cache invalidated. The next
sensitive operation must obtain a current decision; a removed membership does not
reappear through inheritance from the previous snapshot.

## 5. Close out and preserve evidence

- confirm `directory_access.restored` and the new restriction version;
- validate sign-in, organizational area and effective capabilities with a test
  account;
- link platform and Entra evidence to the incident reference;
- review root cause, containment SLA and any delay between the local block and Entra
  actions;
- preserve the audit trail per retention policy.

## Operational recovery

If the executing administrator is the target themselves, they will be blocked after
the commit. Use another emergency access account to restore. If all administrative
accounts are unavailable, follow the corporate access recovery procedure; do not edit
the table manually, as that would break the evidence and the coordinated
invalidation.

## Official references

- [Revoke user access in an emergency](https://learn.microsoft.com/en-us/entra/identity/users/users-revoke-access)
- [`revokeSignInSessions` in Microsoft Graph](https://learn.microsoft.com/en-us/graph/api/user-revokesigninsessions?view=graph-rest-1.0)
- [Continuous Access Evaluation](https://learn.microsoft.com/en-us/entra/identity/conditional-access/concept-continuous-access-evaluation)

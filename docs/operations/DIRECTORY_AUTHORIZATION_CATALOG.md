# Corporate directory authorization catalog

## Purpose

The catalog converts stable Microsoft Entra ID values into platform approval areas.
It is a versioned, fail-closed policy: an App Role, group, name, `department` or any
other unmapped information grants no capability.

The packaged default catalog contains no mappings. An organization must create its
own tenant-specific file, review it, and make it available to the deployment via an
explicit path.

## Structure

Use `docs/examples/entra-authorization-catalog.yaml` as a reference:

```yaml
catalog_id: enterprise-entra-authorization
catalog_version: "2026.08.1"
mappings:
  - mapping_id: entra-role-security-reviewer
    tenant_id: 11111111-1111-4111-8111-111111111111
    source_type: app_role
    source_value: Governance.Security.Reviewer
    approval_area: security
    enabled: true
    owner: identity-and-access-management
    mapping_version: 1
```

Fields:

- `catalog_id`: the policy's stable identity;
- `catalog_version`: full version bumped on every publication;
- `mapping_id`: the mapping's stable identity, used in audit;
- `tenant_id`: UUID of the tenant the mapping belongs to;
- `source_type`: `app_role` or `group`;
- `source_value`: exact App Role value or the group's UUID object ID;
- `approval_area`: value from the corporate `ApprovalArea` taxonomy;
- `enabled`: a real YAML boolean, never text;
- `owner`: area responsible for the source and its review;
- `mapping_version`: positive integer incremented whenever the record changes.

App Roles are case-sensitive. Groups are compared only by canonical object ID.
`displayName`, email, UPN, job title and `department` never participate in the
decision.

## Configuration

The API's access token must contain the configured App Roles claim. For Entra, the
default is `roles`:

```dotenv
OIDC_ENTRA_APP_ROLES_CLAIM=roles
DIRECTORY_AUTHORIZATION_CATALOG_PATH=/run/governance/entra-authorization.yaml
```

Mount the file as read-only in the container. A missing path, invalid YAML, unknown
field, ambiguous type, invalid UUID or duplicate mapping prevents startup. The
application does not fall back to the packaged catalog when the override fails.

`app_role` mappings work only from the verified claim. `group` mappings require
Microsoft Graph to be enabled to resolve transitive memberships. If Graph is
disabled, a complete and validated `groups` claim can also supply the object IDs.
Overage, a missing or invalid claim never grants group capability; if a trusted
Graph snapshot exists, it takes precedence over the token.

## Change workflow

1. IAM confirms the tenant, App Role or object ID, owner and need for access.
2. AI Governance confirms the match to `ApprovalArea` and the area's scope.
3. Security reviews least privilege, segregation of duties and guest impact.
4. The author changes the mapping and increments `mapping_version` and
   `catalog_version`.
5. CI runs YAML validation, domain tests and the full quality gate.
6. Independent reviewers approve the pull request per branch protection.
7. The deployment receives the approved file as read-only configuration and
   restarts.
8. Validation confirms `/api/v1/auth/me`, an allowed decision and a denied decision.

The repository demonstrates the workflow, but the organization needs to configure
the real IAM, Security and AI Governance reviewers in GitHub.

## Audit and minimization

`/api/v1/auth/me` returns:

- effective areas;
- catalog ID and version;
- semantic SHA-256 digest of the catalog;
- IDs of the applied mappings;
- applied source types.

The endpoint does not return raw App Roles, groups, group count or names. An
approval decision records the same provenance in the hash-chained event. This binds
the decision to the policy without persisting the user's full membership
inventory.

## Revocation and rollback

To revoke a capability:

1. disable or remove the mapping;
2. increment the versions;
3. complete an emergency review per the access process;
4. publish and restart the deployment;
5. the new digest makes prior snapshots ineligible;
6. validate that the area disappeared and the decision is denied.

Rollback means republishing a previously approved version of the file, never editing
the Git trail.

To force an immediate revalidation of a single identity, an administrator calls
`POST /api/v1/auth/directory-authorization-cache/invalidate` with `tenant_id`,
`object_id`, an enumerated reason and an optional ticket reference. The operation
clears the snapshot in PostgreSQL and writes an auditable event in the same
transaction, without copying the target's IDs into the event payload. The tenant
must be listed in `OIDC_ALLOWED_TENANT_IDS`. The next sensitive operation must
obtain a fresh, trusted result. This does not remove an App Role, group, session or
account in Entra; definitive revocation remains IAM's responsibility.

If the entire identity needs to be contained, use
`POST /api/v1/auth/directory-access/block`. This command blocks the next protected
request across all replicas, invalidates the cache and writes audit evidence in the
same transaction. Restoration uses `/directory-access/restore` and requires a new
authorization resolution. The full procedure is in
`DIRECTORY_ACCESS_INCIDENT_RESPONSE.md`.

## Minimum validation

- exact App Role grants only the mapped area;
- App Role with different capitalization grants nothing;
- a mapped transitive group grants only with a trusted Graph;
- a group with the same name but a different object ID grants nothing;
- a mapping from another tenant, disabled or duplicated grants nothing;
- guest grants nothing by default;
- an account with unknown type grants nothing;
- catalog or Graph failure blocks the sensitive operation;
- audit contains mapping IDs, version and digest, without raw source values.

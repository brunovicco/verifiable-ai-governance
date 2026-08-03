# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A vendor-independent reference platform for registering, assessing, approving,
documenting and monitoring AI initiatives, systems, models and agents. The MVP turns
governance requirements into verifiable controls, conditional approvals and auditable
evidence. Engineering and governance documentation (`docs/`, ADRs) and code
identifiers are in English; the portal UI (`apps/web`), API user-facing validation
messages, and the business document templates in `packages/document-templates` stay
in Portuguese for their Brazilian end-user audience. `README.pt-BR.md` is the
deliberate Portuguese mirror of the root README. Commit messages remain in
Portuguese per existing convention.

Monorepo layout:

```text
apps/web                     Next.js 16 portal (App Router)
apps/api                     FastAPI backend + persistence (SQLAlchemy async, Alembic)
packages/governance-schemas  Shared enums, policy context/decision, risk breakdown contracts
packages/policy-engine       Deterministic risk classification + declarative control catalog
packages/document-templates  Versioned document templates (YAML manifest)
docs                         Product, governance, architecture (incl. ADRs), operations, backlog
```

Python is managed as a `uv` workspace (root `pyproject.toml` lists `apps/api`,
`packages/governance-schemas`, `packages/policy-engine` as members). The web app is an
npm workspace under `apps/web`.

## Commands

```bash
make setup          # uv sync --all-packages + npm install + seed .env
make dev-api        # uvicorn with --reload on :8000 (needs postgres running)
make dev-web        # next dev, in a separate terminal
make dev            # docker compose up --build (full stack incl. postgres/minio/clamav)
make migrate        # alembic -c apps/api/alembic.ini upgrade head

make test           # pytest (apps/api/tests + packages/policy-engine/tests) + npm run test:web
make lint           # ruff check + mypy strict (api + both packages) + eslint (web)
make format         # ruff format + ruff check --fix
make build          # next build
make quality        # scripts/quality_gate.py - full reproducible gate: uv lock --check,
                     # ruff, mypy, pytest, web test, web lint, web build. This is what CI runs.
```

Single test / narrower runs:

```bash
uv run pytest apps/api/tests/test_inventory.py -k concurrency
uv run pytest packages/policy-engine/tests/test_engine.py
npm run test:web -- lib/labels.test.ts   # vitest, apps/web workspace
```

`apps/api/tests/test_inventory_concurrency_postgres.py` exercises real row locking and
is skipped unless `POSTGRES_TEST_DATABASE_URL` is set (CI provides a postgres service
container for this; locally point it at `docker compose up -d postgres`). All other
Python tests default to an in-memory `sqlite+aiosqlite://` engine set in
`apps/api/tests/conftest.py` and do not require Docker.

Local Keycloak-backed OIDC validation (real token issuance, not mocked):

```bash
make oidc-up      # docker compose -f docker-compose.yml -f docker-compose.oidc.yml up -d postgres keycloak api
make oidc-verify  # scripts/validate_oidc.py - checks real token, group mapping, rejection paths
make oidc-down
```

Backups (portable dump + evidence objects + versioned SHA-256 manifest; never
overwrites an existing target):

```bash
make backup BACKUP_DIR=backups/YYYY-MM-DD
make backup-verify BACKUP_DIR=backups/YYYY-MM-DD
make backup-restore-test BACKUP_DIR=backups/YYYY-MM-DD   # restores into throwaway db/bucket, then cleans up
```

`docker compose up` runs `alembic upgrade head` in a one-shot service before the API
starts; the API only receives traffic if that migration succeeds. Never
`docker compose down -v` as an "update" procedure - it destroys the persisted volume.

## Architecture

### Layering enforced by tests, not just convention

`apps/api/tests/test_architecture.py` parses the AST of every domain/application module
and **asserts** none of them import `fastapi`, `sqlalchemy`, or `pydantic`. This is a
real, enforced Clean Architecture boundary - if you add a new domain or application
module, add it to that test's parametrized list, and if you're tempted to import a
framework type into `domain/` or `application/`, don't; define a port/protocol instead
and implement it in `adapters/`.

The dependency direction for every feature area in `apps/api/src/ai_governance_api/` is:

```
routers/ (FastAPI + Pydantic, thin HTTP adapters)
   -> application/ (use cases: orchestrate transactions, ports, audit - no framework imports)
        -> domain/ (pure types + business rules - no framework imports, no I/O)
adapters/ (SQLAlchemy, PyJWT, boto3, httpx, ClamAV, Microsoft Graph - implement the ports)
dependencies.py is the composition root wiring adapters to application ports
```

Key consequence: application services depend on **ports** (e.g. `PolicyEvaluator`,
`TokenVerifier`, `CorporateDirectoryPort`, `ControlCatalogPort`), not concrete
implementations, so e.g. the deterministic policy engine could be swapped without
touching use cases. Expected/domain errors are raised as stable application-level
categories and only translated to HTTP status codes at the router edge - never raise
`HTTPException` from `application/` or `domain/`.

### Feature areas (each roughly domain -> application -> adapters -> router)

- **Initiatives & policy**: `services/initiatives.py`, `policy-engine` (deterministic,
  no I/O, versioned), `governance-schemas` (shared contracts: `PolicyContext`,
  `PolicyDecision`, `RiskBreakdown`, enums).
- **Structured assessments**: `domain/assessments.py`, `application/assessments.py`,
  `adapters/assessment_persistence.py`. One current assessment per (initiative, type);
  drafts are owner/admin-only, versioned with optimistic concurrency, and immutable once
  submitted until a review round reopens them.
- **Review rounds**: `domain/reviews.py` is pure and framework-free; submission
  snapshots the proposal + assessments immutably and creates round-scoped gates.
  Requesting changes closes the round, replaces pending gates, and reopens assessments;
  a new round only starts once all currently-applicable structured assessments are
  submitted again. Full snapshots are never returned by the history API or copied into
  audit events.
- **Control catalog**: baseline YAML catalog (25 controls) validated against
  `governance-schemas` contracts, loaded once by `policy-engine`, evaluated with
  declarative selectors against the same normalized context used for risk scoring.
  Override path via `CONTROL_CATALOG_PATH`; missing file, invalid schema, duplicate IDs
  or wrong count fail the app closed at startup. A separate, independently-versioned
  `control_crosswalk.yaml` (own contract, own `GovernanceControlCrosswalk` loader,
  `GET /api/v1/controls/crosswalk`, `CONTROL_CROSSWALK_PATH` override) maps each
  control to NIST AI RMF, NIST AI 600-1, OWASP LLM Top 10, OWASP Top 10 for Agentic
  Applications, and MITRE ATLAS - deliberately kept out of the enforcement-critical
  catalog since it's pure reference metadata with no bearing on applicability
  decisions. Citations are grounded in the official source texts (NIST AI 100-1, NIST
  AI 600-1, the OWASP Top 10 for LLM Applications & Generative AI 2025 PDF, the OWASP
  Top 10 for Agentic Applications 2026 PDF, and MITRE ATLAS technique IDs cross-checked
  against both the MITRE SAFE-AI report and OWASP's own ATLAS cross-references), not
  authoritative certification: `agent`-domain controls (`GOV-AGT-*`) cite the Agentic
  Top 10's ASI01-ASI10 codes as their primary OWASP reference, complementing the
  broader LLM Top 10. NIST AI RMF citations stay at function/category granularity by
  deliberate editorial choice (a numbered subcategory is cited only
  where it maps unambiguously), and every reference should still be reconfirmed
  against the official text before formal use. ISO/IEC 42001 is listed in
  `frameworks_pending` and cited nowhere, because it's a licensed standard with no
  accessible source text; a NIST "Critical Infrastructure Profile" exists only as an
  early concept note (no citable categories yet) and is likewise not referenced. The
  loader fails closed if any entry references a `control_id` absent from the loaded
  catalog.
- **Identity & authentication**: `domain/identity.py` holds only immutable identity +
  claim-mapping rules; `application/authentication.py` depends on a `TokenVerifier`
  port; `adapters/oidc.py` implements PyJWT-based JWKS validation (sync, cached, run
  outside the event loop). Only asymmetric algorithms accepted; JWKS requires HTTPS
  outside local/test. Local dev identity requires `APP_ENV=local` plus an explicit
  `X-User-Id` header (and `X-User-Areas` for approvals) - there is no implicit identity.
- **Microsoft Entra / Graph** (corporate auth path, adapter implemented, pending real
  tenant validation): stable identity is `(tenant_id, object_id)`, tenant must be
  allowlisted; `acct` claim classifies member vs guest, guest/ambiguous loses
  approval/admin capabilities by default. `adapters/microsoft_graph.py` implements
  `CorporateDirectoryPort` via OBO with fixed endpoints, timeouts, bounded retries
  (no automatic retry of the OBO exchange itself). Approval areas come **only** from App
  Roles or object IDs explicitly present in the tenant-specific catalog at
  `DIRECTORY_AUTHORIZATION_CATALOG_PATH` (packaged default is empty) - department and
  group names never grant authorization. See `docs/architecture/MICROSOFT_ENTRA_GRAPH_PLAN.md`
  and ADRs 0011–0016.
- **Directory authorization cache**: derived decisions are cached cross-replica in
  Postgres for at most `DIRECTORY_AUTHORIZATION_CACHE_TTL_SECONDS` (default 60s, hard
  cap 5 minutes per architecture doc), keyed to catalog digest, invalidated on admin
  action; never stores tokens, profile, or raw group IDs. ADR 0017.
- **Emergency directory access restriction**: checked after authentication and before
  every protected route, keyed by `(tenant_id, object_id)` in Postgres; a read failure
  blocks the request (fail closed). Blocking/restoring invalidates the authorization
  cache and writes audit evidence in the same transaction. This does not replace
  disabling the account in Entra. ADR 0018; runbook at
  `docs/operations/DIRECTORY_ACCESS_INCIDENT_RESPONSE.md`.
- **Evidence uploads**: transport-independent fail-closed pipeline - bounded read, type
  + signature validation, SHA-256, mandatory ClamAV scan, private S3-compatible object
  storage, transactional metadata write with compensating object delete on failure. The
  original filename is display metadata only; the object key is generated by the
  application. Human-entered evidence *references* stay `trusted_source=false` until
  uploaded and scanned clean.
- **Asset registry / inventory** (`domain/asset_registry.py`, `services/inventory.py`):
  an approved initiative can produce systems; system creation is initiative-owner-only,
  mutations to system/model/agent are system-owner-or-admin-only, all mutating commands
  require `expected_version` (optimistic concurrency). Retirement replaces deletion.
  Model scope is reviewed by Architecture, agent scope by Security, no self-approval by
  the owner; decisions persist a canonical SHA-256 digest of the reviewed scope and a
  risk-proportional validity window. Changing a model materially invalidates dependent
  agents' approvals. All mutating inventory commands take the system row as a
  transactional mutex in Postgres before validating version/dependencies. `review_state`
  is computed at read time so an expired approval is never presented as current. ADRs
  0019–0020.
- **Backups**: same inward-pointing dependency structure - use cases coordinate
  archive/Postgres/object-storage ports, adapters use filesystem/pg_dump/boto3, the CLI
  (`scripts/manage_backups.py`) is the composition root. No distributed transaction
  between Postgres and S3, so the policy requires quiescing writes during capture;
  object count is cross-checked against trusted DB metadata to detect partial backups.
  ADR 0010; runbook at `docs/operations/BACKUP_RESTORE.md`.
- **Model routing**: `domain/model_routing.py`, `application/model_routing.py`,
  `adapters/policy_model_router.py` + `adapters/model_routing_persistence.py`,
  `routers/model_routing.py`, `routing_schemas.py`, alembic revision
  `0008_policy_model_router_decisions.py`. Dual authority: the governance registry
  decides which reviewed `routing_group` values are eligible before any external call;
  the `policy-model-router` service (opt-in, `POLICY_MODEL_ROUTER_ENABLED=false` by
  default) decides which eligible group to use per workflow. Every attempt persists a
  `pending` row before the external call and a single terminal update after; a
  scope-digest mismatch between those two points blocks the decision instead of
  trusting stale facts. No retry of the non-idempotent `/route` POST; any
  unavailability/invalid response fails closed to HTTP 503. ADR 0021.
- **Incidents, kill switch, temporary exceptions**: `domain/incidents.py`,
  `application/incidents.py`, `adapters/incident_persistence.py`,
  `routers/incidents.py`, `incident_schemas.py`, alembic revision
  `0009_incident_management.py`. Incident lifecycle is a validated linear FSM
  (`open → contained → remediating → closed`); closing requires a complete remediation
  plan already on record. `Agent.kill_switch_engaged` (a runtime action) is distinct
  from `Agent.kill_switch_enabled` (a declared capability vetted at Security review) -
  engaging requires the capability to be declared and the incident to still be open.
  Temporary exceptions are always incident-scoped and require purpose, scope,
  compensating controls, and an expiry; persisted status is never rewritten by time -
  validity (`pending`/`active`/`expired`/`rejected`/`revoked`) is computed at read time
  the same way `review_state` is. Deciding an exception requires
  `decided_by != requested_by` and is admin-only (a deliberate simplification versus
  ADR 0002's "committee approval" language - no broader role model exists yet, so
  decide/revoke have no portal UI, matching every other admin-only endpoint in this
  codebase). All mutations reuse the same `ai_systems` row mutex from ADR 0020. ADR
  0022.
- **Operational dashboard**: `application/dashboard.py`,
  `adapters/dashboard_persistence.py`, `dashboard_schemas.py`, `routers/dashboard.py`.
  A single `GET /api/v1/dashboard`, authorized like `GET /api/v1/systems` (any
  authenticated principal, no ownership check - portfolio-wide by design). Aggregates
  four real data sources (routing outcomes/block reasons, review validity by risk
  tier, incident status/overdue remediation, exception validity); review/exception
  validity are recomputed from the same pure domain functions used everywhere else
  (`asset_review_state`, `evaluate_exception_state`), never duplicated in SQL. "Cost"
  surfaces cost-limit-exceeded blocks, not actual spend - no spend-tracking table
  exists. "Drift" is an explicit `drift_available: false` placeholder, not fabricated
  or silently omitted - it depends on the still-unbuilt `ragforge` integration. No
  migration; purely a read aggregation over existing tables. ADR 0023. Also
  aggregates residual risk (`Assessment.risk_tier` - the structured-assessment
  answer, not a separate column), assessment coverage (`Initiative.required_documents`
  ∩ `AssessmentKind` values, deliberately excluding evidence-based document kinds),
  and observed average cycle time for review rounds and incident remediation
  (explicitly "average observed," never "% within SLA" - no target/threshold exists
  anywhere in this codebase to comply against). Control effectiveness gets the same
  explicit-unavailable treatment as drift. ADR 0024.
- **Twelve-Factor properties preserved throughout**: config from environment, stateless
  API processes, Postgres as a swappable backing service, logs as events, dependencies
  declared and reproducible via lockfiles (`uv.lock`, `package-lock.json`).

### Persistence conventions

- Mutable entities carry `version`; decision commands require `expected_version` -
  optimistic concurrency is the norm, not an exception.
- Audit events are append-only and hash-chained (tamper-evidence), never store full
  potentially-sensitive assessment answers or review snapshots.
- `AUTO_CREATE_SCHEMA=false` is the norm; `create_all` is opt-in local convenience only,
  never an upgrade mechanism. Alembic is the only supported way to evolve schema -
  add a new revision under `apps/api/alembic/versions/`.

### Configuration

Deploy config comes entirely from the environment and is validated fail-closed at
startup (`apps/api/src/ai_governance_api/config.py`, `pydantic-settings`). Notable rules
enforced there and exercised in `test_architecture.py`: production rejects
`DEV_AUTH_ENABLED=true`; OIDC is mandatory outside `APP_ENV=local`; object storage
outside local must disable auto-create-bucket and set server-side encryption; secrets
(e.g. `POLICY_MODEL_ROUTER_API_KEYS_JSON`) never leak into `repr(settings)`. `.env` is
local convenience only - see `.env.example` for the full variable catalog.

### Trust boundaries (see `docs/architecture/ARCHITECTURE.md` for the full list)

- The browser is never trusted for authorization or state transitions - the API is the
  sole authority.
- An agent's self-declaration is not evidence; only scanned, hash-verified uploads reach
  `trusted_source=true`.
- Prompt/document content must not enter the operational audit trail by default.

## Where to look first for unfamiliar areas

- `docs/architecture/ARCHITECTURE.md` - narrative architecture, current and accurate;
  read this before touching auth, review rounds, or evidence handling.
- `docs/architecture/adr/` - one ADR per significant decision (numbered, sequential);
  check for an existing ADR before re-litigating a design choice.
- `apps/api/tests/test_architecture.py` - the actual enforced contract for layering and
  fail-closed config; treat it as executable spec, not just tests.

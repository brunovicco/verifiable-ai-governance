# P2.0e.1 Fresh-install migration validation

This guide validates that the Alembic history can build the current schema from a completely
empty PostgreSQL database without a historical checkout, `stamp`, manual table manipulation,
or ORM schema bootstrap.

## Scope

The expected migration graph for this phase is:

```text
0001 -> 0002 -> ... -> 0019 (head)
```

Revision `0001` is now an explicit historical schema contract. `0019` remains the head, so an
existing database already at `0019` does not need recreation.

## Automated fresh-install E2E

From the repository root:

```bash
make fresh-install-e2e
```

or:

```bash
./scripts/test_fresh_install_migrations.sh
```

The script creates a unique Compose project and uses
`ops/compose/p2e1-fresh-install.yml`. PostgreSQL and Redis use container-local `tmpfs`; no
persistent named volume and no host database port are used. Cleanup targets only that unique
P2.0e.1 Compose project.

The E2E performs these checks in order:

1. start isolated PostgreSQL and Runtime Control Redis;
2. assert the PostgreSQL `public` schema contains zero tables;
3. build the API/migration image from the current checkout;
4. run `alembic upgrade head`;
5. run `alembic current` and require `0019 (head)`;
6. run `alembic upgrade head` again and require success;
7. confirm the current revision is still `0019 (head)`;
8. start the API without ORM auto-create;
9. require `GET /health/ready` to report `database=ok`, `schema=ok`, and
   `runtime_control=ok`.

A successful run ends with:

```text
P2.0e.1 fresh-install E2E: PASS
```

## Migration-history unit tests

Run the regression tests independently:

```bash
uv run pytest apps/api/tests/test_migration_history.py
```

They verify the linear revision graph, current head, initial table ownership, and the rule that
migration scripts must not import application ORM models or invoke `create_all`/`drop_all`.

## Validate an existing database safely

For a database that is expected to be at the current head, configure `DATABASE_URL` normally
for that environment and run read-only revision inspection first:

```bash
uv run alembic -c apps/api/alembic.ini current
uv run alembic -c apps/api/alembic.ini heads
```

Expected result for P2.0e.1:

```text
0019 (head)
```

Then the normal deployment migration command is safe:

```bash
uv run alembic -c apps/api/alembic.ini upgrade head
```

If the database was already at `0019`, Alembic does not re-run `0001`; no schema recreation is
required. Run `current` again to record the post-deployment revision.

## API readiness

In a normal environment where the API and required runtime dependencies are running:

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/health/ready
```

The migration-specific E2E already validates the same endpoint from inside its isolated API
container, so it does not need to publish a host port.

## Full validation sequence

After applying the P2.0e.1 files:

```bash
uv run pytest apps/api/tests/test_migration_history.py
./scripts/test_fresh_install_migrations.sh

uv run ruff check .
uv run ruff format --check .

uv run mypy \
  apps/api/src \
  packages/governance-schemas/src \
  packages/policy-engine/src

uv run python scripts/quality_gate.py

git diff --check
git status --short
```

The fresh-install E2E requires Docker with the Compose plugin. The remaining Python gates use
the repository's locked `uv` environment.

## Mandatory Python import guard

P2.0e.1 must not introduce the postponed-annotations future import. Verify the changed
Python files with the repository-required grep command from the implementation request; it
must produce no matches.

## Troubleshooting

### Fresh-database precondition fails

The E2E exits before migrations if its isolated PostgreSQL already contains a public table.
Do not delete tables manually. Allow the script trap to clean its unique project, then rerun
with a new project name or inspect any explicitly supplied `P2E1_COMPOSE_PROJECT_NAME`.

### `alembic current` is not `0019 (head)`

Inspect the migration output and graph test. Do not use `alembic stamp` to force the expected
revision and do not edit `alembic_version` directly.

### API readiness reports schema mismatch

Compare:

```bash
uv run alembic -c apps/api/alembic.ini current
uv run alembic -c apps/api/alembic.ini heads
```

The readiness adapter intentionally fails closed when current and expected heads differ.
Resolve the migration failure instead of disabling readiness checks.

### Docker resources remain after an interrupted test

The script prints its unique Compose project name at startup. Only for that printed P2.0e.1
project, cleanup can be repeated with:

```bash
docker compose \
  --project-name <printed-p2e1-project> \
  --file ops/compose/p2e1-fresh-install.yml \
  down --remove-orphans
```

## Destructive commands to avoid

Do **not** use any of the following against the normal developer stack or a persistent
environment as part of P2.0e.1 validation:

```text
docker compose down -v
DROP TABLE ...
alembic stamp ...
manual UPDATE/DELETE of alembic_version
manual table deletion before migrations
```

The isolated E2E exists specifically so fresh-install validation never needs to destroy the
normal developer database.

## Canonical demo seed

Canonical demo identity determinism is intentionally not changed in P2.0e.1. Fresh-install
migration validation stops after readiness. Deterministic Initiative, AI System, ModelAsset,
and Agent identifiers remain P2.0e.2 scope.

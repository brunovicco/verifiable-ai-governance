# Health checks

The API exposes separate probes for process liveness and runtime readiness.

## Endpoints

| Endpoint | Purpose | Dependency access |
| --- | --- | --- |
| `GET /health/live` | Confirms that the API process can serve HTTP requests. | None |
| `GET /health/ready` | Confirms that the API can safely receive application traffic. | Database connectivity and Alembic schema revision. |
| `GET /health` | Legacy compatibility endpoint. | None |

## Readiness contract

Readiness succeeds only when both conditions are true:

1. the configured database executes a bounded `SELECT 1`; and
2. the database's current Alembic heads exactly match the heads in the deployed
   Alembic revision graph.

The expected revision is not copied into application code. It is loaded through
Alembic's `ScriptDirectory`, using the same `alembic.ini` and migration directory
shipped in the API image.

Successful response:

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "schema": "ok"
  }
}
```

A reachable database with an incompatible schema returns HTTP `503`:

```json
{
  "status": "unavailable",
  "checks": {
    "database": "ok",
    "schema": "mismatch"
  }
}
```

A database connection failure or timeout also returns HTTP `503`:

```json
{
  "status": "unavailable",
  "checks": {
    "database": "unavailable",
    "schema": "not_checked"
  }
}
```

Failure to resolve or parse the deployed Alembic graph returns:

```json
{
  "status": "unavailable",
  "checks": {
    "database": "not_checked",
    "schema": "unavailable"
  }
}
```

Public responses deliberately omit:

- database URLs;
- exception messages;
- credentials;
- current or expected revision identifiers;
- table and column details.

Revision identifiers may be inspected through authenticated operational commands,
not through the public health endpoint.

## Meaning of `schema: mismatch`

Exact set equality is required. `mismatch` therefore covers:

- a database with no `alembic_version` table;
- a database behind the deployed application;
- a database ahead of the deployed application;
- a divergent or partially applied multi-head revision state.

Readiness does not attempt to classify or repair the mismatch.

## Migration ownership

The API process never runs migrations from the health endpoint or application
lifespan. Compose continues to use the one-shot `migrate` service defined by
ADR 0009. Other environments must run an equivalent administrative migration
job before directing traffic to a new application version.

## Recovery

For Compose deployments:

```bash
docker compose logs migrate
docker compose run --rm migrate       alembic -c /workspace/alembic.ini current
docker compose run --rm migrate       alembic -c /workspace/alembic.ini heads
docker compose run --rm migrate       alembic -c /workspace/alembic.ini upgrade head
docker compose restart api
```

Do not use `alembic stamp` to silence readiness unless an operator has independently
verified that the physical schema already matches the target revision. Stamping an
incompatible schema converts a visible deployment failure into latent data and
runtime failures.

## Optional Alembic configuration override

The API resolves Alembic configuration in this order:

1. explicit application/test parameter;
2. `ALEMBIC_CONFIG_PATH`;
3. `/workspace/alembic.ini` or the current working directory;
4. `apps/api/alembic.ini` in a source checkout;
5. the `alembic.ini` adjacent to the API source tree.

When `ALEMBIC_CONFIG_PATH` is configured but invalid, readiness fails closed and
does not fall back to another file.

## Local validation

```bash
uv sync --all-packages --locked
uv run ruff check .
uv run mypy       apps/api/src       packages/governance-schemas/src       packages/policy-engine/src
uv run pytest       apps/api/tests/test_health.py       apps/api/tests/test_runtime_readiness_adapter.py
docker compose config --quiet
```

With the stack running:

```bash
curl --fail http://localhost:8000/health/live
curl --fail http://localhost:8000/health/ready
docker compose ps
```

## Operational semantics

- A liveness failure indicates that the process should be restarted.
- A readiness failure with `database: unavailable` should remove the instance from
  traffic while preserving it for diagnosis.
- A readiness failure with `schema: mismatch` should block rollout and trigger
  migration/deployment investigation.
- The check is bounded and fail-closed.
- Liveness remains independent of database and migration state.

# Health checks

The API exposes separate probes for process health and dependency readiness.

## Endpoints

| Endpoint | Purpose | Dependency access |
| --- | --- | --- |
| `GET /health/live` | Confirms that the API process can serve HTTP requests. | None |
| `GET /health/ready` | Confirms that the API can safely receive application traffic. | Executes `SELECT 1` against the configured database. |
| `GET /health` | Legacy compatibility endpoint. | None |

## Expected responses

Liveness:

```json
{
  "status": "ok"
}
```

Successful readiness:

```json
{
  "status": "ok",
  "checks": {
    "database": "ok"
  }
}
```

Failed readiness returns HTTP `503`:

```json
{
  "status": "unavailable",
  "checks": {
    "database": "unavailable"
  }
}
```

The readiness response deliberately omits exception messages, connection strings and database
implementation details.

## Docker Compose behavior

Docker marks the API healthy only after `/health/ready` succeeds. The web service waits for that
state instead of starting as soon as the API container process exists.

## Local validation

```bash
uv sync --frozen --package ai-governance-api
uv run --package ai-governance-api pytest apps/api/tests/test_health.py
uv run --package ai-governance-api ruff check       apps/api/src/ai_governance_api/routers/health.py       apps/api/tests/test_health.py
uv run --package ai-governance-api mypy apps/api/src
```

With Docker:

```bash
docker compose up --build
curl --fail http://localhost:8000/health/live
curl --fail http://localhost:8000/health/ready
docker compose ps
```

## Operational semantics

- A liveness failure indicates that the process should be restarted.
- A readiness failure indicates that traffic should be withheld, but does not by itself require
  a process restart.
- Database failures and readiness timeouts fail closed with HTTP `503`.
- Schema-version verification is intentionally deferred to backlog item P0.2.

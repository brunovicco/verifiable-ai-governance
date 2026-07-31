FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /workspace
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY packages/governance-schemas/pyproject.toml packages/governance-schemas/pyproject.toml
COPY packages/policy-engine/pyproject.toml packages/policy-engine/pyproject.toml
COPY apps/api/src apps/api/src
COPY packages/governance-schemas/src packages/governance-schemas/src
COPY packages/policy-engine/src packages/policy-engine/src
RUN uv sync --frozen --package ai-governance-api --no-dev --no-editable

FROM python:3.12-slim-bookworm
WORKDIR /workspace
COPY --from=builder /workspace/.venv /workspace/.venv
COPY apps/api/alembic.ini /workspace/alembic.ini
COPY apps/api/alembic /workspace/alembic
ENV PATH="/workspace/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "ai_governance_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

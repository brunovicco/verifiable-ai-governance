.PHONY: setup dev dev-api dev-web test lint format build migrate compose-up compose-down

setup:
	uv sync --all-packages
	npm install
	cp -n .env.example .env || true

dev:
	docker compose up --build

dev-api:
	uv run uvicorn ai_governance_api.main:app --app-dir apps/api/src --reload --port 8000

dev-web:
	npm run dev:web

test:
	uv run pytest
	npm run test:web

lint:
	uv run ruff check .
	uv run mypy apps/api/src packages/governance-schemas/src packages/policy-engine/src
	npm run lint:web

format:
	uv run ruff format .
	uv run ruff check --fix .

build:
	npm run build:web

migrate:
	uv run alembic -c apps/api/alembic.ini upgrade head

compose-up:
	docker compose up --build -d

compose-down:
	docker compose down

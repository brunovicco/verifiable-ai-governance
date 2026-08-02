.PHONY: setup dev dev-api dev-web test lint format build quality migrate compose-up compose-down oidc-up oidc-verify oidc-down backup backup-verify backup-restore-test backup-restore seed-demo

BACKUP_DIR ?= backups/manual

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
	uv run python -m pytest
	npm run test:web

lint:
	uv run python -m ruff check .
	uv run python -m mypy apps/api/src packages/governance-schemas/src packages/policy-engine/src
	npm run lint:web

format:
	uv run ruff format .
	uv run ruff check --fix .

build:
	npm run build:web

quality:
	uv run python scripts/quality_gate.py

migrate:
	uv run alembic -c apps/api/alembic.ini upgrade head

compose-up:
	docker compose up --build -d

compose-down:
	docker compose down

oidc-up:
	docker compose -f docker-compose.yml -f docker-compose.oidc.yml up --build -d postgres keycloak api

oidc-verify:
	uv run python scripts/validate_oidc.py

oidc-down:
	docker compose -f docker-compose.yml -f docker-compose.oidc.yml down

backup:
	uv run python scripts/manage_backups.py create --output "$(BACKUP_DIR)"

backup-verify:
	uv run python scripts/manage_backups.py verify --backup "$(BACKUP_DIR)"

backup-restore-test:
	uv run python scripts/manage_backups.py restore-test --backup "$(BACKUP_DIR)"

backup-restore:
	@test -n "$(RESTORE_DATABASE)" || (echo "RESTORE_DATABASE is required" && exit 2)
	@test -n "$(RESTORE_BUCKET)" || (echo "RESTORE_BUCKET is required" && exit 2)
	uv run python scripts/manage_backups.py restore --backup "$(BACKUP_DIR)" --database "$(RESTORE_DATABASE)" --bucket "$(RESTORE_BUCKET)"

seed-demo:
	uv run python scripts/seed_demo_data.py

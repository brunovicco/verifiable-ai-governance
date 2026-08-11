.PHONY: setup dev dev-api dev-web test lint format build quality migrate fresh-install-e2e compose-up compose-down oidc-up oidc-verify oidc-down backup backup-verify backup-restore-test backup-restore seed-demo seed-demo-check seed-demo-reset seed-demo-gallery

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
	uv run python -m mypy apps/api/src packages/governance-schemas/src packages/policy-engine/src scripts/canonical_demo_seed.py scripts/seed_canonical_demo.py
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

fresh-install-e2e:
	./scripts/test_fresh_install_migrations.sh

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
	uv run python -m scripts.seed_canonical_demo

seed-demo-check:
	uv run python -m scripts.seed_canonical_demo --check

seed-demo-reset:
	uv run python -m scripts.seed_canonical_demo --reset --confirm-reset CANONICAL-DEMO-ONLY

seed-demo-gallery:
	uv run python scripts/seed_demo_data.py

.PHONY: install dev test build openapi database database-local migrate database-check images
UV_CACHE_DIR ?= /private/tmp/staytus-uv-cache
export UV_CACHE_DIR
MIGRATION_ENV ?= .env

install:
	cd backend && uv sync --extra dev
	cd frontend && npm ci

dev:
	node scripts/dev.mjs

test:
	cd backend && uv run pytest -q
	cd frontend && npm run typecheck
	cd backend && uv run python ../scripts/export_openapi_3_0.py --check

build:
	cd frontend && npm run build

openapi:
	cd backend && uv run python ../scripts/export_openapi_3_0.py

database:
	docker compose up -d db

database-local:
	backend/.venv/bin/python scripts/local_postgres.py start

migrate:
	cd backend && uv run python -m app.database_cli --env-file "$(MIGRATION_ENV)" upgrade

database-check:
	cd backend && uv run python -m app.database_cli check

images:
	docker build -f backend/Dockerfile -t staytus-backend:local .
	docker build -f frontend/Dockerfile -t staytus-frontend:local .

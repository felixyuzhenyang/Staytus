.PHONY: install dev test build openapi database
UV_CACHE_DIR ?= /private/tmp/staytus-uv-cache
export UV_CACHE_DIR

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

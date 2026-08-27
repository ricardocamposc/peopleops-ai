.DEFAULT_GOAL := help

help:
	@printf '%s\n' 'Available targets: help install build up down restart ps logs lint format test test-unit test-integration evaluate demo-setup smoke health clean'

evaluate:
	poetry -C apps/peopleops-api run python ../../ops/release_evaluation.py

install:
	poetry -C apps/peopleops-api install
	poetry -C apps/reference-mcp-server install
	cd apps/peopleops-web && npm install

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose down
	docker compose up -d

ps:
	docker compose ps

logs:
	docker compose logs

lint:
	poetry -C apps/peopleops-api run ruff check src tests ../../ops
	poetry -C apps/reference-mcp-server run ruff check src tests
	cd apps/peopleops-web && npm run lint

format:
	poetry -C apps/peopleops-api run ruff format --check src tests ../../ops
	poetry -C apps/reference-mcp-server run ruff format --check src tests
	cd apps/peopleops-web && npm run format

test: test-unit test-integration

test-unit:
	docker compose up -d peopleops-db
	poetry -C apps/peopleops-api run pytest
	poetry -C apps/reference-mcp-server run pytest

test-integration:
	@docker compose config >/dev/null

demo-setup:
	@docker compose exec -T peopleops-api alembic upgrade head
	@docker compose exec -T synthetic-hris-db psql -U "$${SYNTHETIC_HRIS_DATABASE_USER:-synthetic_hris_app}" -d "$${SYNTHETIC_HRIS_DATABASE_NAME:-synthetic_hris}" < synthetic-hris/seeds/seed.sql
	@docker compose exec -T synthetic-hris-db psql -U "$${SYNTHETIC_HRIS_DATABASE_USER:-synthetic_hris_app}" -d "$${SYNTHETIC_HRIS_DATABASE_NAME:-synthetic_hris}" < synthetic-hris/alternate-schema/migration.sql
	@docker compose exec -T synthetic-hris-db psql -U "$${SYNTHETIC_HRIS_DATABASE_USER:-synthetic_hris_app}" -d "$${SYNTHETIC_HRIS_DATABASE_NAME:-synthetic_hris}" < synthetic-hris/alternate-schema/seed.sql
	@printf '%s\n' 'Demo databases ready. See docs/portfolio/DEMO-SCRIPT.md for policy upload and scenarios.'

smoke:
	poetry -C apps/peopleops-api run python ../../ops/release_smoke.py

health:
	curl --fail --silent --show-error http://localhost:$${API_PORT:-8000}/api/v1/health
	curl --fail --silent --show-error http://localhost:$${MCP_PORT:-8001}/health
	curl --fail --silent --show-error http://localhost:$${WEB_PORT:-3000}/

clean:
	docker compose down --volumes --remove-orphans

.PHONY: help install build up down restart ps logs lint format test test-unit test-integration evaluate demo-setup smoke health clean

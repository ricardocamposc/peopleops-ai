.DEFAULT_GOAL := help

help:
	@printf '%s\n' 'Available targets: help install build up down restart ps logs lint format test test-unit test-integration health clean'

install:
	poetry -C apps/peopleops-api install
	poetry -C apps/reference-mcp-server install
	cd apps/peopleops-web && pnpm install

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
	poetry -C apps/peopleops-api run ruff check src tests
	poetry -C apps/reference-mcp-server run ruff check src tests
	cd apps/peopleops-web && pnpm lint

format:
	poetry -C apps/peopleops-api run ruff format --check src tests
	poetry -C apps/reference-mcp-server run ruff format --check src tests
	cd apps/peopleops-web && pnpm format

test: test-unit test-integration

test-unit:
	poetry -C apps/peopleops-api run pytest
	poetry -C apps/reference-mcp-server run pytest

test-integration:
	@docker compose config >/dev/null

health:
	curl --fail --silent --show-error http://localhost:$${API_PORT:-8000}/api/v1/health
	curl --fail --silent --show-error http://localhost:$${MCP_PORT:-8001}/health

clean:
	docker compose down --volumes --remove-orphans

.PHONY: help install build up down restart ps logs lint format test test-unit test-integration health clean

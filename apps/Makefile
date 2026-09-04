.DEFAULT_GOAL := help

ROOT := $(abspath $(CURDIR)/..)

API_PORT ?= 8000
MCP_PORT ?= 8001
WEB_PORT ?= 3000
PEOPLEOPS_DB_PORT ?= 5436
SYNTHETIC_HRIS_DB_PORT ?= 5437
PROMPT_TEST_PORT ?= 8765

help:
	@printf '%s\n' 'Available targets: help infra stop-apps migrate migrate-hris seed-hris generate-policy-pdfs regenerate-fictitious-policy-pdfs clear-policy-records demo-setup run api mcp web prompt-test'

# Docker is used only for the two PostgreSQL services by the local workflow.
infra:
	docker compose -f $(ROOT)/docker-compose.yml up -d peopleops-db synthetic-hris-db

migrate:
	cd peopleops-api && set -a && [ ! -f ../../.env ] || . ../../.env && set +a; \
	export PEOPLEOPS_DATABASE_HOST=127.0.0.1 PEOPLEOPS_DATABASE_PORT=$(PEOPLEOPS_DB_PORT); \
	poetry run alembic upgrade head

migrate-hris:
	cd $(ROOT)/synthetic-hris && set -a && [ ! -f ../.env ] || . ../.env && set +a; \
	export SYNTHETIC_HRIS_DATABASE_URL=postgresql+psycopg://$${SYNTHETIC_HRIS_DATABASE_USER:-synthetic_hris_app}:$${SYNTHETIC_HRIS_DATABASE_PASSWORD:-synthetic_hris_local_placeholder}@127.0.0.1:$(SYNTHETIC_HRIS_DB_PORT)/$${SYNTHETIC_HRIS_DATABASE_NAME:-synthetic_hris}; \
	poetry -C ../apps/peopleops-api run alembic -c alembic.ini upgrade head

seed-hris:
	set -a && [ ! -f $(ROOT)/.env ] || . $(ROOT)/.env && set +a; \
	docker compose -f $(ROOT)/docker-compose.yml exec -T synthetic-hris-db \
	psql -U "$${SYNTHETIC_HRIS_DATABASE_USER:-synthetic_hris_app}" \
	-d "$${SYNTHETIC_HRIS_DATABASE_NAME:-synthetic_hris}" < $(ROOT)/synthetic-hris/seeds/seed.sql

generate-policy-pdfs:
	python3 $(ROOT)/ops/generate_policy_pdfs.py --output-dir $(ROOT)/policies/generated

regenerate-fictitious-policy-pdfs:
	python3 $(ROOT)/ops/regenerate_fictitious_policy_pdfs.py --corpus-dir $(ROOT)/policies/fictitious-company

clear-policy-records:
	cd peopleops-api && set -a && [ ! -f ../../.env ] || . ../../.env && set +a; \
	export PEOPLEOPS_DATABASE_HOST=127.0.0.1 PEOPLEOPS_DATABASE_PORT=$(PEOPLEOPS_DB_PORT); \
	PYTHONPATH=src poetry run python ../../ops/clear_policy_records.py --yes

demo-setup: infra migrate migrate-hris seed-hris

# Starts only the databases and then runs the API directly on the host.
run: infra api

stop-apps:
	docker compose -f $(ROOT)/docker-compose.yml stop peopleops-api peopleops-web reference-mcp-server

api:
	cd peopleops-api && set -a && [ ! -f ../../.env ] || . ../../.env && set +a; \
	export API_PORT=$(API_PORT) MCP_PORT=$(MCP_PORT) PEOPLEOPS_DATABASE_HOST=127.0.0.1 PEOPLEOPS_DATABASE_PORT=$(PEOPLEOPS_DB_PORT); \
	export REFERENCE_MCP_SERVER_URL=http://127.0.0.1:$(MCP_PORT); \
	PYTHONPATH=src poetry run uvicorn peopleops_api.main:app --host 127.0.0.1 --port "$(API_PORT)"

mcp:
	cd reference-mcp-server && set -a && [ ! -f ../../.env ] || . ../../.env && set +a; \
	export SYNTHETIC_HRIS_DATABASE_HOST=127.0.0.1 SYNTHETIC_HRIS_DATABASE_PORT=$(SYNTHETIC_HRIS_DB_PORT); \
	PYTHONPATH=src poetry run uvicorn reference_mcp_server.main:app --host 127.0.0.1 --port "$(MCP_PORT)"

web:
	cd peopleops-web && npm run dev -- --hostname 127.0.0.1 --port "$(WEB_PORT)"

prompt-test:
	cd peopleops-api && set -a && [ ! -f ../../.env ] || . ../../.env && set +a; \
	PYTHONPATH=src poetry run python ../../evaluation/spikes/semantic_run_viewer.py --port "$(PROMPT_TEST_PORT)"

.PHONY: help infra stop-apps migrate migrate-hris seed-hris generate-policy-pdfs regenerate-fictitious-policy-pdfs clear-policy-records demo-setup run api mcp web prompt-test

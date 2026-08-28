.DEFAULT_GOAL := help

help:
	@printf '%s\n' 'Available targets: help install build up up-all run api mcp web infra stop-apps migrate migrate-hris seed-hris generate-policy-pdfs regenerate-fictitious-policy-pdfs clear-policy-records demo-setup down restart ps logs lint format test test-unit test-integration evaluate baseline-policy-rag baseline-hris-mcp baseline-mcp baseline-combined baseline-all baseline-policy baseline-policy-judge baseline-judge baseline-structured-hr baseline-structured-hr-holdout publish-structured-hr-baseline inspect-policy-run smoke health clean'

infra:
	$(MAKE) -C apps infra

run:
	$(MAKE) -C apps run

api:
	$(MAKE) -C apps api

stop-apps:
	docker compose stop peopleops-api peopleops-web reference-mcp-server

mcp:
	$(MAKE) -C apps mcp

web:
	$(MAKE) -C apps web

migrate:
	$(MAKE) -C apps migrate

migrate-hris:
	$(MAKE) -C apps migrate-hris

seed-hris:
	$(MAKE) -C apps seed-hris

generate-policy-pdfs:
	python3 ops/generate_policy_pdfs.py --output-dir policies/generated

regenerate-fictitious-policy-pdfs:
	python3 ops/regenerate_fictitious_policy_pdfs.py --corpus-dir policies/fictitious-company

clear-policy-records:
	$(MAKE) -C apps clear-policy-records

evaluate:
	poetry -C apps/peopleops-api run python ../../ops/release_evaluation.py

baseline-policy:
	PYTHONPATH=src poetry -C apps/peopleops-api run python ../../ops/policy_rag_baseline.py --dataset "$(abspath $(if $(POLICY_DATASET),$(POLICY_DATASET),evaluation/cases/policy_rag_fictitious_company_v1.jsonl))" --output-dir "$(abspath $(if $(POLICY_BASELINE_OUTPUT_DIR),$(POLICY_BASELINE_OUTPUT_DIR),evaluation/runs/baseline-$(shell date +%Y%m%d-%H%M%S)))"

baseline: baseline-policy

baseline-policy-rag: baseline-policy

baseline-policy-rag-holdout:
	PYTHONPATH=src poetry -C apps/peopleops-api run python ../../ops/policy_rag_baseline.py --dataset "$(abspath evaluation/cases/policy_rag_holdout_v1.jsonl)" --output-dir "$(abspath $(if $(POLICY_HOLDOUT_OUTPUT_DIR),$(POLICY_HOLDOUT_OUTPUT_DIR),evaluation/runs/holdout-$(shell date +%Y%m%d-%H%M%S)))"

baseline-policy-rag-validation:
	PYTHONPATH=src poetry -C apps/peopleops-api run python ../../ops/policy_rag_baseline.py --dataset "$(abspath evaluation/cases/policy_rag_holdout_v1.jsonl)" --output-dir "$(abspath $(if $(POLICY_VALIDATION_OUTPUT_DIR),$(POLICY_VALIDATION_OUTPUT_DIR),evaluation/runs/validation-$(shell date +%Y%m%d-%H%M%S)))"

baseline-policy-rag-holdout-v2:
	PYTHONPATH=src poetry -C apps/peopleops-api run python ../../ops/policy_rag_baseline.py --dataset "$(abspath evaluation/cases/policy_rag_holdout_v2.jsonl)" --output-dir "$(abspath $(if $(POLICY_HOLDOUT_V2_OUTPUT_DIR),$(POLICY_HOLDOUT_V2_OUTPUT_DIR),evaluation/runs/holdout-v2-$(shell date +%Y%m%d-%H%M%S)))"

publish-policy-baseline:
	PYTHONPATH=apps/peopleops-api/src poetry -C apps/peopleops-api run python ../../ops/publish_policy_baseline.py --run-dir "$(POLICY_RUN_DIR)" --baseline-name "$(POLICY_BASELINE_NAME)"

baseline-hris-mcp:
	PYTHONPATH=src poetry -C apps/peopleops-api run python -m peopleops_api.evaluation_runner --dataset "$(abspath evaluation/cases/hris_mcp_mvp_v1.jsonl)" --output-dir "$(abspath $(if $(HRIS_BASELINE_OUTPUT_DIR),$(HRIS_BASELINE_OUTPUT_DIR),evaluation/runs/hris-mcp-$(shell date +%Y%m%d-%H%M%S)))" --baseline "$(abspath evaluation/baselines/hris-mcp-mvp.json)"

baseline-mcp:
	PYTHONPATH=apps/peopleops-api/src poetry -C apps/peopleops-api run python ../../ops/mcp_boundary_baseline.py --dataset "$(abspath evaluation/cases/mcp_boundary_v1.jsonl)" --output-dir "$(abspath $(if $(MCP_BASELINE_OUTPUT_DIR),$(MCP_BASELINE_OUTPUT_DIR),evaluation/runs/mcp-$(shell date +%Y%m%d-%H%M%S)))" --base-url "$(if $(MCP_BASE_URL),$(MCP_BASE_URL),http://127.0.0.1:$${MCP_PORT:-8001})" --alternate-url "$(MCP_ALTERNATE_URL)"

publish-mcp-baseline:
	PYTHONPATH=apps/peopleops-api/src poetry -C apps/peopleops-api run python ../../ops/publish_mcp_baseline.py --run-dir "$(MCP_RUN_DIR)" --baseline-name "$(MCP_BASELINE_NAME)" --baselines-dir "$(abspath evaluation/baselines/mcp)"

baseline-combined:
	PYTHONPATH=src poetry -C apps/peopleops-api run python -m peopleops_api.evaluation_runner --dataset "$(abspath evaluation/cases/peopleops_combined_mvp_v1.jsonl)" --output-dir "$(abspath $(if $(COMBINED_BASELINE_OUTPUT_DIR),$(COMBINED_BASELINE_OUTPUT_DIR),evaluation/runs/combined-$(shell date +%Y%m%d-%H%M%S)))" --baseline "$(abspath evaluation/baselines/combined-mvp.json)"

baseline-all: baseline-policy-rag baseline-hris-mcp baseline-combined

baseline-structured-hr:
	PYTHONPATH=apps/peopleops-api/src poetry -C apps/peopleops-api run python ../../ops/structured_hr_baseline.py --dataset "$(abspath evaluation/cases/structured_hr_analysis_v2.jsonl)" --output-dir "$(abspath $(if $(STRUCTURED_HR_OUTPUT_DIR),$(STRUCTURED_HR_OUTPUT_DIR),evaluation/runs/structured-hr-$(shell date +%Y%m%d-%H%M%S)))" --base-url "$(if $(PEOPLEOPS_API_URL),$(PEOPLEOPS_API_URL),http://127.0.0.1:$${API_PORT:-8000})"

baseline-structured-hr-holdout:
	PYTHONPATH=apps/peopleops-api/src poetry -C apps/peopleops-api run python ../../ops/structured_hr_baseline.py --dataset "$(abspath evaluation/cases/structured_hr_holdout_v1.jsonl)" --output-dir "$(abspath $(if $(STRUCTURED_HR_HOLDOUT_OUTPUT_DIR),$(STRUCTURED_HR_HOLDOUT_OUTPUT_DIR),evaluation/runs/structured-hr-holdout-$(shell date +%Y%m%d-%H%M%S)))" --base-url "$(if $(PEOPLEOPS_API_URL),$(PEOPLEOPS_API_URL),http://127.0.0.1:$${API_PORT:-8000})"

publish-structured-hr-baseline:
	PYTHONPATH=apps/peopleops-api/src poetry -C apps/peopleops-api run python ../../ops/publish_structured_baseline.py --run-dir "$(STRUCTURED_HR_RUN_DIR)" --baseline-name "$(STRUCTURED_HR_BASELINE_NAME)"

baseline-policy-judge:
	PYTHONPATH=apps/peopleops-api/src poetry -C apps/peopleops-api run python ../../ops/judge_policy_baseline.py --predictions $${POLICY_PREDICTIONS:-evaluation/runs/baseline-local/predictions.jsonl} --output-dir $${POLICY_BASELINE_OUTPUT_DIR:-evaluation/runs/baseline-local} --allow-synthetic-data

baseline-judge: baseline-policy-judge

inspect-policy-run:
	@test -n "$(POLICY_RUN_ID)" || (printf '%s\n' 'POLICY_RUN_ID is required' >&2; exit 1)
	PYTHONPATH=apps/peopleops-api/src poetry -C apps/peopleops-api run python ../../ops/inspect_policy_evaluation_run.py --run-id "$(POLICY_RUN_ID)" --output "$(if $(POLICY_RUN_OUTPUT),$(POLICY_RUN_OUTPUT),evaluation/runs/$(POLICY_RUN_ID)/database-evidence.json)"

install:
	poetry -C apps/peopleops-api install
	poetry -C apps/reference-mcp-server install
	cd apps/peopleops-web && npm install

build:
	docker compose build

up: infra

up-all:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose down
	$(MAKE) infra

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
	$(MAKE) infra migrate migrate-hris seed-hris
	@printf '%s\n' 'Demo databases ready. See docs/portfolio/DEMO-SCRIPT.md for policy upload and scenarios.'

smoke:
	poetry -C apps/peopleops-api run python ../../ops/release_smoke.py

health:
	curl --fail --silent --show-error http://localhost:$${API_PORT:-8000}/api/v1/health
	curl --fail --silent --show-error http://localhost:$${MCP_PORT:-8001}/health
	curl --fail --silent --show-error http://localhost:$${WEB_PORT:-3000}/

clean:
	docker compose down --volumes --remove-orphans

.PHONY: help install build up up-all run api mcp web infra stop-apps migrate migrate-hris seed-hris generate-policy-pdfs clear-policy-records down restart ps logs lint format test test-unit test-integration evaluate baseline-policy-rag baseline-policy-rag-validation baseline-policy-rag-holdout baseline-policy-rag-holdout-v2 publish-policy-baseline publish-mcp-baseline baseline-hris-mcp baseline-mcp baseline-combined baseline-all baseline-policy baseline baseline-policy-judge baseline-judge baseline-structured-hr baseline-structured-hr-holdout publish-structured-hr-baseline inspect-policy-run demo-setup smoke health clean

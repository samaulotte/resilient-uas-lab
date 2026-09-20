# Resilient UAS Lab - developer task runner.
# Every target here is exercised in CI or documented in docs/development.md.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE ?= docker compose
UV ?= uv
PNPM ?= pnpm
REPORTS_DIR ?= artifacts/reports
BASELINE_DIR ?= artifacts/baseline

.PHONY: help setup dev up down logs ps test test-python test-web test-integration lint format \
        typecheck build e2e demo sim observability report regression schemas gen-client \
        docker-build clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install Python and JavaScript dependencies (uv + pnpm)
	$(UV) sync --all-packages
	$(PNPM) install --frozen-lockfile

dev: ## Run API, orchestrator, runner and web dev server against local infrastructure (see docs/development.md)
	@echo "Infrastructure: $(COMPOSE) up -d postgres nats objectstore"
	@echo "Then in separate terminals:"
	@echo "  $(UV) run python -m reslab_platform.db.cli migrate-and-seed"
	@echo "  $(UV) run python -m reslab_api.main"
	@echo "  $(UV) run python -m reslab_orchestrator.main"
	@echo "  $(UV) run python -m reslab_runner.main"
	@echo "  NEXT_PUBLIC_API_BASE=http://localhost:8000 $(PNPM) --filter @reslab/web dev"

up: ## Start the platform (control plane, Mission Control, mock runner)
	$(COMPOSE) up --build -d
	@echo "Mission Control: http://localhost:$${RESLAB_GATEWAY_PORT:-8080}"

down: ## Stop the platform and remove containers (volumes are kept)
	$(COMPOSE) --profile sim --profile observability down --remove-orphans

logs: ## Follow platform logs
	$(COMPOSE) logs -f --tail=200

ps: ## Show service status
	$(COMPOSE) ps

test: test-python test-web ## Run Python and frontend unit tests

test-python: ## Run Python unit tests
	$(UV) run pytest -q

test-web: ## Run frontend unit tests
	$(PNPM) --filter @reslab/web test

test-integration: ## Run the mock pipeline integration tests against running infrastructure
	RESLAB_INTEGRATION=1 $(UV) run pytest tests/integration -q -m integration

lint: ## Lint Python (ruff) and TypeScript (eslint)
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(PNPM) --filter @reslab/web lint
	$(PNPM) format:check

format: ## Format Python and TypeScript sources
	$(UV) run ruff format .
	$(UV) run ruff check --fix .
	$(PNPM) format

typecheck: ## TypeScript type checking (client + web)
	$(PNPM) -r typecheck

build: ## Build the web application
	$(PNPM) build

e2e: ## Run Playwright end-to-end tests against the running platform (RESLAB_E2E_BASE_URL, default http://localhost:8080)
	$(PNPM) exec playwright test -c tests/e2e/playwright.config.ts

demo: ## Queue the compound-degradation demo scenario on the running platform
	$(UV) run reslab run compound-degradation --api $${RESLAB_API_URL:-http://localhost:8080}

sim: ## Start the platform with the PX4 SITL / Gazebo simulation profile (Linux)
	$(COMPOSE) --profile sim up --build -d

observability: ## Start the observability profile (Prometheus, Grafana)
	$(COMPOSE) --profile observability up -d

report: ## Execute every starter scenario in-process and write reports to $(REPORTS_DIR)
	scripts/run_scenarios_local.sh $(REPORTS_DIR)

regression: ## Compare $(REPORTS_DIR) against $(BASELINE_DIR) using regression-thresholds.yaml
	$(UV) run reslab regression check --candidate $(REPORTS_DIR) $(if $(wildcard $(BASELINE_DIR)),--baseline $(BASELINE_DIR),) --thresholds regression-thresholds.yaml

schemas: ## Export JSON Schemas and the OpenAPI document to packages/schemas/
	RESLAB_LOG_LEVEL=WARNING $(UV) run python scripts/export_schemas.py

gen-client: schemas ## Regenerate the TypeScript API client from the OpenAPI document
	$(PNPM) gen:client

docker-build: ## Build all container images
	$(COMPOSE) --profile sim build

clean: ## Remove build outputs, caches and local artifacts
	rm -rf apps/web/.next apps/web/coverage artifacts .reslab
	find . -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache tests/e2e/test-results tests/e2e/playwright-report

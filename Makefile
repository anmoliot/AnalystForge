SHELL := /bin/sh
PYTHON ?= python
UV ?= uv
COMPOSE ?= docker compose

.DEFAULT_GOAL := help
.PHONY: help env up down restart logs ps build migrate revision test test-python test-web e2e \
	lint lint-python lint-web typecheck format coverage bootstrap dev-api dev-web shell psql \
	redis-cli sdk-test ingest seed-demo backup restore clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

env: ## Generate .env with random secrets if missing
	@$(PYTHON) scripts/gen_env.py

bootstrap: ## Install Python (uv) and web (npm) dependencies locally
	$(UV) sync --all-packages
	cd apps/web && npm install

up: env ## Build and start the full stack
	$(COMPOSE) up -d --build
	@echo ""
	@echo "AnalystForge is starting:"
	@echo "  App:      http://localhost:8080"
	@echo "  API docs: http://localhost:8080/docs"
	@echo "  Mailpit:  http://localhost:8025"
	@echo "Run 'make logs' to follow startup."

down: ## Stop the stack (volumes retained)
	$(COMPOSE) down

restart: ## Restart the stack
	$(COMPOSE) restart

logs: ## Follow service logs
	$(COMPOSE) logs -f --tail=200

ps: ## Show service status
	$(COMPOSE) ps

build: ## Rebuild application images
	$(COMPOSE) build

migrate: ## Apply database migrations
	$(UV) run alembic -c apps/api/alembic.ini upgrade head

revision: ## Create an Alembic revision (m="message")
	$(UV) run alembic -c apps/api/alembic.ini revision --autogenerate -m "$(m)"

test: test-python test-web ## Run all unit and integration tests

test-python: ## Run Python tests
	$(UV) run pytest

test-web: ## Run frontend tests
	cd apps/web && npm test -- --run

e2e: ## Run Playwright end-to-end tests (stack must be up)
	cd apps/web && npx playwright test

lint: lint-python lint-web ## Lint everything

lint-python: ## Ruff + mypy
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy packages/quant/src

lint-web: ## ESLint + TypeScript
	cd apps/web && npm run lint && npm run typecheck

typecheck: ## Python and TypeScript strict type checks
	$(UV) run mypy packages/quant/src
	cd apps/web && npm run typecheck

format: ## Auto-format Python and web code
	$(UV) run ruff format .
	$(UV) run ruff check --fix .
	cd apps/web && npm run format

coverage: ## Python coverage report (quant gate: 95%)
	$(UV) run pytest --cov=analystforge.quant --cov-report=term-missing --cov-report=html

dev-api: ## Run the API natively with reload
	$(UV) run uvicorn analystforge.api.main:app --reload --host 127.0.0.1 --port 8000

dev-web: ## Run the Vite dev server
	cd apps/web && npm run dev

shell: ## Open a shell in the API container
	$(COMPOSE) exec api bash

psql: ## Open psql against the compose database
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-analystforge} -d $${POSTGRES_DB:-analystforge}

redis-cli: ## Open redis-cli in the compose Redis
	$(COMPOSE) exec redis redis-cli

sdk-test: ## Run Python SDK integration tests against a running API
	$(UV) run pytest packages/sdk-python/tests -m "sdk or not sdk"

ingest: ## Run the default ingestion job manually
	$(COMPOSE) exec api python -m analystforge.worker.cli ingest-all

seed-demo: ## Load the clearly-labelled demo dataset (never used by default)
	$(COMPOSE) exec api python -m analystforge.worker.cli seed-demo

backup: ## Dump the database to var/backups
	./scripts/backup.sh

restore: ## Restore from var/backups (file=...)
	./scripts/restore.sh "$(file)"

clean: ## Remove local caches and build artefacts (not volumes)
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov coverage.xml
	rm -rf apps/web/dist apps/web/playwright-report apps/web/test-results
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

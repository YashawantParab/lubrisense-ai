.PHONY: up down restart ps logs build \
	migrate seed seed-knowledge demo-reset \
	backend-install backend-test backend-lint backend-typecheck backend-format \
	frontend-install frontend-lint frontend-typecheck frontend-build frontend-format \
	simulator-install simulator-test simulator-lint simulator-typecheck simulator-format \
	edge-install edge-test edge-lint edge-typecheck edge-format \
	ml-service-install ml-service-test ml-service-lint ml-service-typecheck ml-service-format \
	mqtt-verify kafka-verify pipeline-verify data-quality-verify baseline-verify rules-verify \
	verify

COMPOSE ?= docker compose

## --- Platform lifecycle ---

up: ## Start the full local platform stack
	$(COMPOSE) up -d

down: ## Stop and remove the local platform stack
	$(COMPOSE) down

restart: down up ## Restart the local platform stack

ps: ## Show service status
	$(COMPOSE) ps

logs: ## Follow logs for all services
	$(COMPOSE) logs -f

build: ## Build all service images
	$(COMPOSE) build

## --- Database ---

migrate: ## Run Alembic migrations against the running database
	cd backend && uv run alembic upgrade head

seed: ## Load the deterministic demo asset hierarchy (idempotent)
	cd backend && uv run python scripts/seed_demo_data.py

seed-knowledge: ## Load the approved knowledge corpus (idempotent)
	cd backend && uv run python scripts/seed_knowledge_corpus.py

demo-reset: ## One deterministic command for the complete demo-ready state (stack, migrations, base data, knowledge, flagship story)
	./scripts/demo-reset.sh

## --- Backend ---

backend-install: ## Install backend dependencies
	cd backend && uv sync --extra dev

backend-test: ## Run backend test suite (requires postgres + redis running)
	cd backend && uv run pytest

backend-lint: ## Lint backend code
	cd backend && uv run ruff check .

backend-typecheck: ## Type-check backend code
	cd backend && uv run mypy app

backend-format: ## Auto-format backend code
	cd backend && uv run ruff format .

## --- Frontend ---

frontend-install: ## Install frontend dependencies
	cd frontend && npm install

frontend-lint: ## Lint frontend code
	cd frontend && npm run lint

frontend-typecheck: ## Type-check frontend code
	cd frontend && npm run typecheck

frontend-build: ## Production build the frontend
	cd frontend && npm run build

frontend-format: ## Auto-format frontend code
	cd frontend && npm run format

## --- Simulator ---

simulator-install: ## Install simulator dependencies
	cd simulator && uv sync --extra dev

simulator-test: ## Run simulator test suite (requires postgres running + demo data seeded)
	cd simulator && uv run pytest

simulator-lint: ## Lint simulator code
	cd simulator && uv run ruff check .

simulator-typecheck: ## Type-check simulator code
	cd simulator && uv run mypy simulator

simulator-format: ## Auto-format simulator code
	cd simulator && uv run ruff format .

## --- Edge ---

edge-install: ## Install edge dependencies
	cd edge && uv sync --extra dev

edge-test: ## Run edge test suite (unit; requires postgres + mosquitto running for -m mqtt/db tests)
	cd edge && uv run pytest

edge-lint: ## Lint edge code
	cd edge && uv run ruff check .

edge-typecheck: ## Type-check edge code
	cd edge && uv run mypy edge

edge-format: ## Auto-format edge code
	cd edge && uv run ruff format .

## --- ML Service ---

ml-service-install: ## Install ml-service dependencies
	cd ml-service && uv sync --extra dev

ml-service-test: ## Run ml-service test suite (pure Python, no live Docker dependency)
	cd ml-service && uv run pytest

ml-service-lint: ## Lint ml-service code
	cd ml-service && uv run ruff check .

ml-service-typecheck: ## Type-check ml-service code
	cd ml-service && uv run mypy ml_service

ml-service-format: ## Auto-format ml-service code
	cd ml-service && uv run ruff format .

## --- Messaging verification ---

mqtt-verify: ## Prove MQTT publish/subscribe works against the running broker
	./scripts/verify_mqtt.sh

kafka-verify: ## Prove Kafka produce/consume works against the running broker
	./scripts/verify_kafka.sh

pipeline-verify: ## Prove the telemetry pipeline is idempotent/replay-safe/outage-resilient (requires full stack up + seed)
	./scripts/verify_pipeline.sh

data-quality-verify: ## Prove the Phase 7 data-quality engine detects synthetic issues live (requires full stack up + seed)
	./scripts/verify_data_quality.sh

baseline-verify: ## Prove the Phase 8 baseline engine builds/updates baselines live (requires full stack up + seed)
	./scripts/verify_baselines.sh

rules-verify: ## Prove the Phase 9 rules engine produces/lifecycles findings live (requires full stack up + seed)
	./scripts/verify_rules.sh

## --- Aggregate ---

test: backend-test simulator-test edge-test ml-service-test ## Run all automated test suites

lint: backend-lint frontend-lint simulator-lint edge-lint ml-service-lint ## Run all linters

typecheck: backend-typecheck frontend-typecheck simulator-typecheck edge-typecheck ml-service-typecheck ## Run all type checkers

verify: lint typecheck test frontend-build mqtt-verify kafka-verify pipeline-verify data-quality-verify baseline-verify rules-verify ## Run the full verification suite

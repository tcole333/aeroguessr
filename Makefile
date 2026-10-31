# Makefile

.PHONY: help demo dev frontend backend start stop openapi ws-schema integration-test sample-replay

# Default target: Show help
help:
	@echo "Available targets:"
	@echo "  demo          Run the game locally with synthetic planes (Redis, API, ingest, Vite); Ctrl-C stops"
	@echo "  dev           Same as demo, but with the settings in .env as they are"
	@echo "                Both pick free ports unless DEV_API_PORT, DEV_WEB_PORT or DEV_REDIS_PORT is set;"
	@echo "                NETWORK=1 opens the game to the LAN"
	@echo "  frontend      Start only the Vite dev server"
	@echo "  backend       Start only the API"
	@echo "  start         Build and start the production Docker stack (nginx, frontend, backend, redis)"
	@echo "  stop          Stop the Docker stack"
	@echo "                Both use the Compose project $(COMPOSE_PROJECT); integration-test adds _test"
	@echo "  openapi       Generate docs/api_openapi.yaml"
	@echo "  ws-schema     Generate docs/ws_schema.yaml"
	@echo "  integration-test  Run the integration suite in Docker"
	@echo "  sample-replay Run the sample ADS-B generator on its own (requires FAKE_ADSB=1)"

# Each checkout runs its own Compose projects, named after its directory, so a worktree's stacks
# never share containers or volumes with another checkout's. The Pi's deploy doesn't use these
# targets: infra/docker-compose.pi.yml keeps its project name, infra.
COMPOSE_PROJECT := $(shell scripts/checkout-env.sh project)
ifeq ($(COMPOSE_PROJECT),)
$(error scripts/checkout-env.sh printed no Compose project name)
endif
COMPOSE = docker compose -p $(COMPOSE_PROJECT) -f infra/docker-compose.yml

# Run the whole game locally in one terminal (scripts/dev.sh).
demo:
	@scripts/dev.sh demo

dev:
	@scripts/dev.sh live

frontend:
	@cd frontend && npm run dev

backend:
	@uv run uvicorn backend.app:app --reload --host 127.0.0.1 --port $${DEV_API_PORT:-8000}

# Target to start all services using Docker Compose
start:
	@echo "--- Starting all services (nginx, frontend, backend, redis) as Compose project $(COMPOSE_PROJECT) ---"
	@$(COMPOSE) up --build -d
	@echo "Application available at http://localhost"
	@echo "Backend API docs at http://localhost/api/v0/docs (via nginx proxy)"

# Target to stop all services
stop:
	@echo "--- Stopping all services ---"
	@$(COMPOSE) down

# Target to generate OpenAPI specification. Both generators run as modules: uv doesn't install
# the project, so backend/ imports only from the repo root, which python -m puts on the path.
openapi:
	@echo "--- Generating OpenAPI specification ---"
	@uv run python -m backend.scripts.generate_openapi
	@echo "----------------------------------------"

# Target to generate WS schema
ws-schema:
	@echo "--- Generating WebSocket schema ---"
	@uv run python -m backend.scripts.gen_ws_schema
	@echo "-------------------------------------"

TEST_COMPOSE ?= docker compose -p $(COMPOSE_PROJECT)_test -f infra/docker-compose.test.yml

# Run integration tests inside docker-compose. The whole recipe is one shell, so the target
# exits non-zero when the stack fails to start, the backend never answers, or any test fails.
# Container logs always go to logs/integration.log and the stack is always torn down.
integration-test:
	@mkdir -p logs
	@status=0; \
	echo "--- Building and starting integration test services ---"; \
	{ $(TEST_COMPOSE) build && $(TEST_COMPOSE) up -d; } || status=$$?; \
	if [ $$status -eq 0 ]; then \
		echo "--- Waiting up to 30s for the backend to answer ---"; \
		ready=false; \
		for _ in $$(seq 1 30); do \
			if $(TEST_COMPOSE) exec -T backend-test curl -s -o /dev/null http://localhost:8000/healthz; then \
				ready=true; break; \
			fi; \
			sleep 1; \
		done; \
		if [ "$$ready" != true ]; then \
			echo "ERROR: backend-test did not answer /healthz within 30s."; \
			status=1; \
		fi; \
	fi; \
	if [ $$status -eq 0 ]; then \
		echo "--- Running integration tests ---"; \
		$(TEST_COMPOSE) exec -T backend-test bash -c \
			"cd /app && uv run pytest -vv -m integration" || status=$$?; \
	fi; \
	echo "--- Collecting container logs ---"; \
	$(TEST_COMPOSE) logs --no-color > logs/integration.log 2>&1 || true; \
	echo "--- Tearing down integration test services ---"; \
	$(TEST_COMPOSE) down -v --remove-orphans || true; \
	echo "--- Integration test run finished (exit code: $$status) ---"; \
	exit $$status

# Run the sample ADS-B generator on its own. FAKE_ADSB_FILE means what it does to the
# ingest: "synthetic" (the default) or a capture to replay.
sample-replay:
	@if [ "$$FAKE_ADSB" != "1" ]; then \
		echo "Please set FAKE_ADSB=1 before running sample replay"; \
		exit 1; \
	fi
	@FILE=$${FAKE_ADSB_FILE:-synthetic}; \
	SPEED=$${FAKE_ADSB_SPEED:-1.0}; \
	uv run python -m sample_data.adsb_generator --file $$FILE --speed $$SPEED --loop

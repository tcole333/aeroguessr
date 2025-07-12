# Makefile

.PHONY: help openapi integration-test ws-schema sample-replay frontend backend dev start stop

# Default target: Show help
help:
	@echo "Available targets:"
	@echo "  start         Start all services (nginx, frontend, backend, redis) using Docker Compose"
	@echo "  stop          Stop all running services"
	@echo "  dev           Start all services in development mode"
	@echo "  dev-network   Start all services in development mode (network accessible, auto-detects IP)"
	@echo "  frontend      Start frontend development server"
	@echo "  frontend-network  Start frontend development server (network accessible)"
	@echo "  backend       Start backend development server"
	@echo "  backend-network   Start backend development server (network accessible WebSocket URLs)"
	@echo "  openapi       Generate OpenAPI specification (docs/api_openapi.yaml)"
	@echo "  help          Show this help message"
	@echo "  integration-test    Spin up test services and run integration tests"
	@echo "  ws-schema     Generate WebSocket schema (docs/ws_schema.yaml)"
	@echo "  sample-replay Run sample ADS-B generator (requires FAKE_ADSB=1)"

# Target to start frontend development server
frontend:
	@echo "--- Starting frontend development server ---"
	@cd frontend && npm run dev

# Target to start frontend development server with network access
frontend-network:
	@echo "--- Starting frontend development server (network accessible) ---"
	@cd frontend && npm run dev -- --host 0.0.0.0

# Target to start backend development server
backend:
	@echo "--- Starting backend development server ---"
	@poetry run uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# Target to start backend development server with network WebSocket URLs
backend-network:
	@echo "--- Starting backend development server (network accessible WebSocket URLs) ---"
	@if [ -z "$$NETWORK_IP" ]; then \
		echo "❌ NETWORK_IP not set. This target should be called from dev-network or with NETWORK_IP set."; \
		exit 1; \
	fi; \
	echo "🌐 WebSocket URLs will use: ws://$$NETWORK_IP:8000/"; \
	WS_BASE_URL="ws://$$NETWORK_IP:8000/" poetry run uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000

# Target to start all services in development mode
dev:
	@echo "--- Starting all services in development mode ---"
	@docker compose -f infra/docker-compose.yml up redis -d
	@make backend & make frontend

# Target to start all services in development mode with network access
dev-network:
	@echo "--- Starting all services in development mode (network accessible) ---"
	@# Auto-detect IP address (prioritize private network ranges)
	@DETECTED_IP=$$(ifconfig 2>/dev/null | grep -E "inet (192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)" | head -1 | awk '{print $$2}' | sed 's/addr://'); \
	if [ -z "$$DETECTED_IP" ]; then \
		DETECTED_IP=$$(ip route get 1 2>/dev/null | grep -Po 'src \K\S+' | head -1); \
	fi; \
	if [ -z "$$DETECTED_IP" ]; then \
		echo "❌ Could not automatically detect IP address"; \
		echo "Please manually set NETWORK_IP environment variable:"; \
		echo "export NETWORK_IP=192.168.1.100  # Replace with your actual IP"; \
		exit 1; \
	fi; \
	echo "🔍 Detected IP address: $$DETECTED_IP"; \
	docker compose -f infra/docker-compose.yml up redis -d; \
	NETWORK_IP=$$DETECTED_IP make backend-network & NETWORK_IP=$$DETECTED_IP make frontend-network

# Target to start all services using Docker Compose
start:
	@echo "--- Starting all services (nginx, frontend, backend, redis) ---"
	@docker compose -f infra/docker-compose.yml up --build -d
	@echo "Application available at http://localhost"
	@echo "Backend API docs at http://localhost/api/v0/docs (via nginx proxy)"

# Target to stop all services
stop:
	@echo "--- Stopping all services ---"
	@docker compose -f infra/docker-compose.yml down

# Target to generate OpenAPI specification
openapi:
	@echo "--- Generating OpenAPI specification ---"
	@poetry run python backend/scripts/generate_openapi.py
	@echo "----------------------------------------"

# Target to generate WS schema
ws-schema:
	@echo "--- Generating WebSocket schema ---"
	@poetry run python backend/scripts/gen_ws_schema.py
	@echo "-------------------------------------"

# Add other common targets like lint, test, build, etc. here later

# Run integration tests inside docker-compose. If pytest fails, capture
# container logs to ``logs/integration.log`` for post-mortem before tearing down.
integration-test:
ifeq ($(SANDBOX_ENV),true)
	@echo "--- (Sandbox) Starting integration test services (expecting pre-built images) ---"
	@docker compose -f infra/docker-compose.test.yml up -d --no-build
else
	@echo "--- Building and starting integration test services ---"
	@docker compose -f infra/docker-compose.test.yml build # Builds services with 'build' config, pulls others
	@docker compose -f infra/docker-compose.test.yml up -d
endif
	@echo "--- Waiting for backend service to be healthy ---"
	@# Add a wait loop for the health check - waits up to 30s
	@timeout=30; \
	start_time=$$(date +%s); \
	while ! curl -sf http://localhost:8000/healthz > /dev/null; do \
	    if [ $$(($$(date +%s) - $$start_time)) -ge $$timeout ]; then \
	        echo "ERROR: Backend service did not become healthy after $$timeout seconds."; \
	        docker compose -f infra/docker-compose.test.yml logs --no-color > logs/integration.log || true; \
	        docker compose -f infra/docker-compose.test.yml down -v --remove-orphans || true; \
	        exit 1; \
	    fi; \
	    echo -n '.'; \
	    sleep 1; \
	done
	@echo " Backend Healthy!"
	@echo "--- Running integration tests ---"
	@# Run pytest using exec. Store exit code.
	@set -e; \
	TEST_CMD="cd /app && PYTHONPATH=/app poetry run pytest -vv -m integration"; \
	pytest_exit_code=0; \
	docker compose -f infra/docker-compose.test.yml exec backend-test bash -c "$$TEST_CMD" || pytest_exit_code=$$?;
	@echo "--- Collecting container logs ---"
	@docker compose -f infra/docker-compose.test.yml logs --no-color > logs/integration.log
	@echo "--- Tearing down integration test services ---"
	@docker compose -f infra/docker-compose.test.yml down -v --remove-orphans
	@echo "--- Integration test run finished (Exit code: $$pytest_exit_code) ---"
	@# Exit with the captured pytest exit code
	@exit $$pytest_exit_code

# Convenience target to run sample ADS-B generator for local dev
sample-replay:
	@if [ "$$FAKE_ADSB" != "1" ]; then \
		echo "Please set FAKE_ADSB=1 before running sample replay"; \
		exit 1; \
	fi
	@FILE=$${FAKE_ADSB_FILE:-sample_data/sbs_parser_fixtures.sbs}; \
	SPEED=$${FAKE_ADSB_SPEED:-1.0}; \
	poetry run python -m sample_data.adsb_generator --file $$FILE --speed $$SPEED --loop

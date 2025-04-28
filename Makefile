# Makefile

.PHONY: help openapi integration-test ws-schema

# Default target: Show help
help:
	@echo "Available targets:"
	@echo "  openapi    Generate OpenAPI specification (docs/api_openapi.yaml)"
	@echo "  help       Show this help message"
	@echo "  integration-test    Spin up test services and run integration tests"
	@echo "  ws-schema    Generate WebSocket schema (docs/ws_schema.yaml)"

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

integration-test:
	@echo "--- Building and starting integration test services ---"
	@docker compose -f infra/docker-compose.test.yml build
	@docker compose -f infra/docker-compose.test.yml up -d
	@echo "--- Running integration tests ---"
	@docker compose -f infra/docker-compose.test.yml exec backend-test bash -c "cd /app && PYTHONPATH=/app poetry run pytest -q -m integration"
	@echo "--- Tearing down integration test services ---"
	@docker compose -f infra/docker-compose.test.yml down

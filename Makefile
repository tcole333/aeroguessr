# Makefile

.PHONY: help openapi integration-test ws-schema sample-replay

# Default target: Show help
help:
	@echo "Available targets:"
	@echo "  openapi    Generate OpenAPI specification (docs/api_openapi.yaml)"
	@echo "  help       Show this help message"
	@echo "  integration-test    Spin up test services and run integration tests"
	@echo "  ws-schema    Generate WebSocket schema (docs/ws_schema.yaml)"
	@echo "  sample-replay  Run sample ADS-B generator (requires FAKE_ADSB=1)"

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
# container logs to ``logs.txt`` for post-mortem before tearing down.
integration-test:
	@echo "--- Building and starting integration test services ---"
	@docker compose -f infra/docker-compose.test.yml build
	@docker compose -f infra/docker-compose.test.yml up -d
	@echo "--- Running integration tests ---"
	@set -e; \
	TEST_CMD="cd /app && PYTHONPATH=/app poetry run pytest -q -m integration"; \
	docker compose -f infra/docker-compose.test.yml exec backend-test bash -c "$$TEST_CMD" || (\
		echo "Integration tests FAILED – collecting container logs to logs.txt"; \
		docker compose -f infra/docker-compose.test.yml logs --no-color > logs.txt; \
		docker compose -f infra/docker-compose.test.yml down; \
		exit 1); \
		true
	@echo "--- Tearing down integration test services ---"
	@docker compose -f infra/docker-compose.test.yml down

# Convenience target to run sample ADS-B generator for local dev
sample-replay:
	@if [ "$$FAKE_ADSB" != "1" ]; then \
		echo "Please set FAKE_ADSB=1 before running sample replay"; \
		exit 1; \
	fi
	@FILE=$${FAKE_ADSB_FILE:-sample_data/sbs_parser_fixtures.sbs}; \
	SPEED=$${FAKE_ADSB_SPEED:-1.0}; \
	poetry run python -m sample_data.adsb_generator --file $$FILE --speed $$SPEED --loop

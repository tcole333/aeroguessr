# Makefile

.PHONY: help openapi

# Default target: Show help
help:
	@echo "Available targets:"
	@echo "  openapi    Generate OpenAPI specification (docs/api_openapi.yaml)"
	@echo "  help       Show this help message"

# Target to generate OpenAPI specification
openapi:
	@echo "--- Generating OpenAPI specification ---"
	@poetry run python backend/scripts/generate_openapi.py
	@echo "----------------------------------------"

# Add other common targets like lint, test, build, etc. here later

import logging
from pathlib import Path

import yaml

from backend.app import app  # Import the FastAPI app instance

logger = logging.getLogger(__name__)


def generate_openapi_spec() -> None:
    """Generates the OpenAPI spec and writes it to docs/api_openapi.yaml."""

    # Ensure the docs directory exists relative to the project root
    project_root = Path(__file__).parent.parent.parent
    output_dir = project_root / "docs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "api_openapi.yaml"

    logger.info(f"Generating OpenAPI spec for '{app.title}' v{app.version}...")

    # Get the OpenAPI schema as a dictionary
    openapi_schema = app.openapi()

    # Errors propagate, so `make openapi` fails instead of leaving the committed spec in
    # place for CI's drift check to pass against.
    yaml_schema = yaml.dump(openapi_schema, sort_keys=False, allow_unicode=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(yaml_schema)
    logger.info(f"✅ OpenAPI spec successfully written to: {output_path}")


if __name__ == "__main__":
    # Configure basic logging for script execution
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    generate_openapi_spec()

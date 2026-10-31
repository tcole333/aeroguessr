"""Contract tests for the REST surface under /api/v0/rooms.

Room state, including the current round's answer, reaches clients only through the
WebSocket protocol. REST offers exactly create and join, in the served schema and in
the committed docs/api_openapi.yaml.
"""

from pathlib import Path

import yaml

from backend.app import app

OPENAPI_DOC_PATH = Path(__file__).resolve().parents[3] / "docs" / "api_openapi.yaml"

ROOM_REST_OPERATIONS = {
    ("post", "/api/v0/rooms"),
    ("post", "/api/v0/rooms/{room_code}/join"),
}


def _room_operations(openapi_schema: dict) -> set[tuple[str, str]]:
    return {
        (method, path)
        for path, operations in openapi_schema["paths"].items()
        if path.startswith("/api/v0/rooms")
        for method in operations
    }


def test_served_openapi_offers_only_create_and_join_room_operations() -> None:
    assert _room_operations(app.openapi()) == ROOM_REST_OPERATIONS


def test_committed_openapi_doc_offers_only_create_and_join_room_operations() -> None:
    committed_schema = yaml.safe_load(OPENAPI_DOC_PATH.read_text(encoding="utf-8"))

    assert _room_operations(committed_schema) == ROOM_REST_OPERATIONS

"""Generate docs/ws_schema.yaml from Pydantic models.

Run via `make ws-schema`.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Dict, Type
import yaml  # PyYAML
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)
# Path to output YAML
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "docs" / "ws_schema.yaml"

# Import the ws schemas module dynamically
ws_module = importlib.import_module("backend.schemas.ws")

# Map message type strings to payload model classes. Update as new types are added.
MESSAGE_PAYLOAD_MAP: Dict[str, Type[BaseModel]] = {
    "stateSync": ws_module.FullRoomState,
    "delta": getattr(ws_module, "DeltaPayload", None),
    "roundStart": ws_module.RoundStartPayload,
    "roundResult": ws_module.RoundResultPayload,
    "playerJoined": ws_module.PlayerJoinedPayload,
    "playerLeft": ws_module.PlayerLeftPayload,
    "newHost": ws_module.NewHostPayload,
    "error": ws_module.ErrorPayload,
    "pong": ws_module.PingPongPayload,
    "ping": ws_module.PingPongPayload,
    "guess": ws_module.GuessPayload,
    "selectPlane": ws_module.SelectPlanePayload,
    "startRound": ws_module.StartRoundPayload,
    "skipRound": getattr(ws_module, "SkipRoundPayload", None),
    "transferHost": ws_module.TransferHostPayload,
    "claimHost": ws_module.ClaimHostPayload,
    "leave": ws_module.LeavePayload,
    "planeSelectedConfirm": getattr(ws_module, "PlaneSelectedConfirmPayload", None),
}

# Remove None entries (if optional classes missing)
# ruff: noqa
MESSAGE_PAYLOAD_MAP = {
    k: v
    for k, v in MESSAGE_PAYLOAD_MAP.items()
    if v is not None  # type: ignore[arg-type]
}

# Build $defs with JSON Schema for each unique model
unique_models = {cls for cls in MESSAGE_PAYLOAD_MAP.values()}

defs: Dict[str, Any] = {}
for model_cls in unique_models:
    schema = model_cls.model_json_schema(ref_template="#/$defs/{model}")
    defs[model_cls.__name__] = schema

# Build messages mapping referencing $defs
messages: Dict[str, Dict[str, Any]] = {}
for msg_type, model_cls in MESSAGE_PAYLOAD_MAP.items():
    messages[msg_type] = {"payload": {"$ref": f"#/$defs/{model_cls.__name__}"}}

schema_doc = {
    "title": "Plane Game WebSocket Schema",
    "version": 1,
    "messages": messages,
    "$defs": defs,
}

# Dump to YAML (safe)
OUTPUT_PATH.write_text(yaml.safe_dump(schema_doc, sort_keys=False))
logger.info(f"Wrote {OUTPUT_PATH}")

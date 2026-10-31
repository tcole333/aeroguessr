"""Generate docs/ws_schema.yaml from Pydantic models.

Run via `make ws-schema`.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, Dict, Type

import yaml  # PyYAML
from pydantic import BaseModel

logger = logging.getLogger(__name__)
# Path to output YAML
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "docs" / "ws_schema.yaml"

# Import the ws schemas module dynamically
ws_module = importlib.import_module("backend.schemas.ws")

# Map message type strings to payload model classes. Update as new types are added.
MESSAGE_PAYLOAD_MAP: Dict[str, Type[BaseModel]] = {
    "stateSync": ws_module.FullRoomState,
    "delta": ws_module.DeltaPayload,
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
    "skipRound": ws_module.SkipRoundPayload,
    "transferHost": ws_module.TransferHostPayload,
    "claimHost": ws_module.ClaimHostPayload,
    "leave": ws_module.LeavePayload,
    "planeSelectedConfirm": ws_module.PlaneSelectedConfirmPayload,
}

# A message type missing here would vanish from the schema, and CI's drift check would
# still pass, so the map must name exactly the WSMessageType values.
mismatched = {t.value for t in ws_module.WSMessageType} ^ MESSAGE_PAYLOAD_MAP.keys()
if mismatched:
    raise SystemExit(
        f"MESSAGE_PAYLOAD_MAP and WSMessageType disagree on: {', '.join(sorted(mismatched))}"
    )

# Build $defs with JSON Schema for each unique model, sorted so the output is stable
unique_models = sorted(set(MESSAGE_PAYLOAD_MAP.values()), key=lambda cls: cls.__name__)

defs: Dict[str, Any] = {}
for model_cls in unique_models:
    schema = model_cls.model_json_schema(ref_template="#/$defs/{model}")
    defs[model_cls.__name__] = schema

# Build messages mapping referencing $defs
messages: Dict[str, Dict[str, Any]] = {}
for msg_type, model_cls in MESSAGE_PAYLOAD_MAP.items():
    messages[msg_type] = {"payload": {"$ref": f"#/$defs/{model_cls.__name__}"}}

schema_doc = {
    "title": "AeroGuessr WebSocket Schema",
    "version": 1,
    "messages": messages,
    "$defs": defs,
}

# Dump to YAML (safe)
OUTPUT_PATH.write_text(yaml.safe_dump(schema_doc, sort_keys=False))
logger.info(f"Wrote {OUTPUT_PATH}")

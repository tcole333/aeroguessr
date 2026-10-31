# ruff: noqa: D101, D103
"""Integration tests verifying plane `delta` broadcasts.

We manipulate Redis plane keys and ensure the backend broadcasts the
expected ``delta`` WebSocket messages (``updated`` / ``removed``).  The
backend broadcast task runs at 1 s intervals, so generous timeouts are
used to avoid flakes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set

import pytest
import redis.asyncio as redis
from fastapi import status
from httpx import AsyncClient
from httpx_ws import aconnect_ws

from backend.schemas.core import ScoringMode
from backend.schemas.plane import PlaneState, PublicPlaneState
from backend.schemas.ws import DeltaPayload, PingPongPayload, WSMessage

from .ws_helpers import wait_for_message

pytestmark = pytest.mark.integration
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _extract_updated_hexes(updated_list: List[PublicPlaneState | Dict[str, Any]]) -> Set[str]:
    """Extract ``hex_ident`` strings from the ``updated`` list.

    ``broadcast_plane_updates`` serialises ``PublicPlaneState`` objects, so on
    the wire we receive dicts.  Pydantic will coerce them back to
    ``PublicPlaneState`` if we use ``DeltaPayload``, but they can also appear as
    raw dicts in the ``msg.payload`` JSON.  This helper supports both.
    """

    hexes: Set[str] = set()
    for item in updated_list:
        if isinstance(item, PublicPlaneState):
            hexes.add(item.hex_ident)
        elif isinstance(item, dict):
            # Fallback – assume key exists.
            maybe_hex = item.get("hex_ident")
            if maybe_hex:
                hexes.add(str(maybe_hex))
    return hexes


async def _await_delta(
    ws: Any,  # noqa: ANN401 - an httpx_ws.AsyncWebSocketSession, kept generic
    *,
    expected_updated: Optional[Set[str]] = None,
    expected_removed: Optional[Set[str]] = None,
    timeout: float = 12.0,
) -> DeltaPayload:
    """Wait until a ``delta`` message satisfies expectations.

    Args:
        ws: Active WebSocket session.
        expected_updated: ``hex_ident`` values that **must** appear in
            ``planes.updated``.
        expected_removed: ``hex_ident`` values that **must** appear in
            ``planes.removed``.
        timeout: Max seconds to wait.

    Returns:
        The payload that satisfied the criteria.

    Raises:
        asyncio.TimeoutError: If timeout reached before matching message.
    """

    expected_updated = expected_updated or set()
    expected_removed = expected_removed or set()

    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError("Timeout waiting for expected delta message.")

        raw = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
        msg = WSMessage(**raw)

        if msg.type == "ping":
            # Echo pong to keep the server happy.
            pong = WSMessage(type="pong", payload=PingPongPayload(**msg.payload).model_dump())
            await ws.send_json(pong.model_dump())
            continue
        if msg.type != "delta":
            continue  # Ignore unrelated messages.

        payload = DeltaPayload(**msg.payload)
        planes = payload.planes or {}
        updated_hexes = _extract_updated_hexes(planes.get("updated", []))
        removed_hexes = set(planes.get("removed", []))

        if expected_updated.issubset(updated_hexes) and expected_removed.issubset(removed_hexes):
            return payload


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delta_broadcast_sequence(
    integration_client: AsyncClient, real_redis: redis.Redis
) -> None:
    """Full add→update→remove flow for two dummy planes."""

    host_nick = "host_delta"
    plane_a = "abc123"
    plane_b = "def456"

    # ------------------------------------------------------------------
    # 1. Host creates room via REST.
    # ------------------------------------------------------------------
    resp = await integration_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": host_nick,
            "mode": ScoringMode.EXACT.value,
            "round_timeout_seconds": 15,
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED
    room_code = resp.json()["room_code"]
    ws_path = f"/api/v0/rooms/ws/{room_code}/{host_nick}"

    # Precompute Redis keys.
    key_a = f"plane:{plane_a}"
    key_b = f"plane:{plane_b}"

    # ------------------------------------------------------------------
    # 2. Connect host WebSocket and consume initial stateSync.
    # ------------------------------------------------------------------
    async with aconnect_ws(ws_path, client=integration_client) as ws:
        await wait_for_message(ws, "stateSync")

        # ----------------------------------------------------------------
        # 3. Scenario 1 – add two new planes.
        # ----------------------------------------------------------------
        now = time.time()
        dummy_a = PlaneState(
            hex_ident=plane_a,
            lat=42.0,
            lon=-71.0,
            alt=20000,
            lat_v=0,
            lon_v=0,
            alt_v=0,
            last_update_ts=now,
            trail=[],
        )
        dummy_b = PlaneState(
            hex_ident=plane_b,
            lat=43.0,
            lon=-72.0,
            alt=22000,
            lat_v=0,
            lon_v=0,
            alt_v=0,
            last_update_ts=now,
            trail=[],
        )
        await real_redis.set(key_a, dummy_a.model_dump_json(), ex=60)
        await real_redis.set(key_b, dummy_b.model_dump_json(), ex=60)

        await _await_delta(ws, expected_updated={plane_a, plane_b}, timeout=12.0)

        # ----------------------------------------------------------------
        # 4. Scenario 2 – modify altitude of plane A.
        # ----------------------------------------------------------------
        updated_a = dummy_a.model_copy(update={"alt": 25000, "last_update_ts": time.time()})
        await real_redis.set(key_a, updated_a.model_dump_json(), ex=60)

        payload2 = await _await_delta(ws, expected_updated={plane_a}, timeout=12.0)
        # Ensure only A is in updated list.
        planes2 = payload2.planes or {}
        assert {plane_a} == _extract_updated_hexes(planes2.get("updated", []))

        # ----------------------------------------------------------------
        # 5. Scenario 3 – remove plane B.
        # ----------------------------------------------------------------
        await real_redis.delete(key_b)
        await _await_delta(ws, expected_removed={plane_b}, timeout=12.0)

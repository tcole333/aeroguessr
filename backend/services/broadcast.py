"""Background task for broadcasting plane state updates to connected clients."""

import asyncio
import logging
from typing import Dict, List

from pydantic import BaseModel, Field

from backend.ingest.main import PlaneState  # Assuming PlaneState is defined here

# Import the specific payload schema and WSMessage wrapper
from backend.schemas.ws import WSMessage
from backend.services.plane_filter import PlaneFilter
from backend.utils.connection_manager import ConnectionManager
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)

# How often to fetch and prepare updates (in seconds)
BROADCAST_INTERVAL_SECONDS = 1.0


# Define the structure for the delta update payload
class PlaneDeltaUpdate(BaseModel):
    updated: List[PlaneState] = Field(default_factory=list)
    removed: List[str] = Field(default_factory=list)  # List of hex_idents


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------


async def _get_current_plane_state_map(
    redis_client: RedisClient,
) -> Dict[str, PlaneState]:
    """Return a mapping of ``hex_ident -> PlaneState`` for all ``plane:*`` keys.

    Notes:
        We *cannot* rely on :pymeth:`redis.asyncio.Redis.scan_iter` because it
        hangs indefinitely when the connection pool is initialised with
        ``decode_responses=True`` – see redis-py issue GH-2389.  A safe
        workaround is to page manually via SCAN.

    Args:
        redis_client: Wrapper that provides pooled Redis connections.

    Returns:
        Dict mapping ICAO24 hex identifiers to their deserialised
        :class:`backend.ingest.main.PlaneState` representation.
    """

    current_state: Dict[str, PlaneState] = {}

    # Manual paging – SCAN returns (new_cursor, List[keys]).
    cursor = 0
    async with await redis_client.get_connection() as conn:
        while True:
            cursor, keys = await conn.scan(cursor=cursor, match="plane:*", count=1000)
            logger.debug("[BCAST DEBUG] SCAN returned %d keys (cursor=%d)", len(keys), cursor)
            for key in keys:
                # Keys can be bytes when decode_responses=False – normalise.
                key_str = key.decode() if isinstance(key, (bytes, bytearray)) else str(key)

                plane = await redis_client.get_model(key_str, PlaneState)
                if plane:
                    current_state[plane.hex_ident] = plane
            if cursor == 0:
                break

    logger.debug("Fetched %d current plane states via SCAN paging.", len(current_state))
    return current_state


async def broadcast_plane_updates(redis_client: RedisClient, manager: ConnectionManager) -> None:
    """Periodically fetches plane states, calculates deltas, and broadcasts to all rooms.

    This task runs indefinitely until the application shuts down. It fetches all
    `plane:*` keys, compares them to the previous state to find changes (new,
    updated, removed planes), and broadcasts these deltas via the ConnectionManager
    to all currently active rooms.

    Args:
        redis_client: The asynchronous Redis client instance.
        manager: The WebSocket connection manager instance.
    """
    logger.info("Starting plane update broadcast task...")
    last_state: Dict[str, PlaneState] = {}
    plane_filter = PlaneFilter(redis_client)

    while True:
        try:
            start_time = asyncio.get_event_loop().time()

            # --- Task 42: Fetch Current Plane States ---
            # Use safe paging helper (avoids redis-py scan_iter bug)
            current_state_map = await _get_current_plane_state_map(redis_client)
            logger.info(f"Fetched {len(current_state_map)} planes from Redis")

            # --- NEW: Filter stale planes based on range and signal quality ---
            stale_planes = await plane_filter.filter_stale_planes(current_state_map)
            if stale_planes:
                logger.info(f"Filtering {len(stale_planes)} stale planes: {stale_planes}")
                await plane_filter.remove_planes_from_redis(stale_planes)

            # --- Task 43: Calculate Delta --- #
            updated_planes: List[PlaneState] = []
            removed_plane_hexes: List[str] = []

            # Create a filtered state map without stale planes for comparison
            filtered_state_map = {
                hex_id: plane
                for hex_id, plane in current_state_map.items()
                if hex_id not in stale_planes
            }

            # Check for updated and new planes (using filtered state)
            for hex_ident, current_plane in filtered_state_map.items():
                last_plane = last_state.get(hex_ident)
                # Add if new or if changed since last time
                # Using Pydantic's default __ne__ which compares model fields
                if last_plane is None or current_plane != last_plane:
                    updated_planes.append(current_plane)

            # Check for removed planes (present in last state but not in filtered current)
            # Include both naturally removed planes and stale planes that were filtered
            removed_plane_hexes_set = set()

            # Add planes that were in last_state but not in current (including stale)
            for hex_ident in last_state:
                if hex_ident not in filtered_state_map:
                    removed_plane_hexes_set.add(hex_ident)

            # Also add stale planes that were just filtered out
            removed_plane_hexes_set.update(stale_planes)

            # Convert back to list for the delta payload
            removed_plane_hexes = list(removed_plane_hexes_set)

            delta = PlaneDeltaUpdate(updated=updated_planes, removed=removed_plane_hexes)

            if delta.updated or delta.removed:
                logger.debug(
                    f"Delta calculated: {len(delta.updated)} updated, {len(delta.removed)} removed."
                )
            else:
                logger.info("No changes detected in plane states.")

            # Update last_state for the next iteration (use filtered state)
            last_state = filtered_state_map

            # --- Task 44: Broadcast Delta --- #
            if delta.updated or delta.removed:
                logger.debug(
                    f"Delta has {len(delta.updated)} updated "
                    f"and {len(delta.removed)} removed planes"
                )
                # Serialise PlaneState models to primitives for safe JSON encoding
                planes_updated_serialised = [p.model_dump() for p in delta.updated]
                payload_dict = {
                    "planes": {
                        "updated": planes_updated_serialised,
                        "removed": delta.removed,
                    }
                }
                ws_message = WSMessage(type="delta", payload=payload_dict)

                logger.debug(
                    f"Preparing to broadcast delta: {ws_message.model_dump_json(exclude_none=True)}"
                )

                # TODO: Implement compression for payloads > 1KB (Task #44)

                # Get active rooms and broadcast to each one
                active_room_codes = list(manager.active_connections.keys())  # Get codes first
                if not active_room_codes:
                    logger.debug("No active rooms to broadcast to.")
                else:
                    logger.debug(f"Broadcasting delta to rooms: {active_room_codes}")
                    for room_code in active_room_codes:
                        try:
                            # Pass the specific room_code to the broadcast method
                            await manager.broadcast(
                                message=ws_message.model_dump(exclude_none=True),
                                room_code=room_code,
                            )
                            logger.info(
                                f"[BCAST] Delta broadcasted to room '{room_code}' with "
                                f"{len(delta.updated)} updated / {len(delta.removed)} removed"
                                + (f" - removed: {delta.removed}" if delta.removed else "")
                            )
                        except Exception as broadcast_error:
                            # Log error specific to this room, but continue broadcasting to others
                            logger.error(
                                f"Error broadcasting delta to room '{room_code}': "
                                f"{broadcast_error}",
                                exc_info=True,
                            )

            # --- Loop Timing ---
            end_time = asyncio.get_event_loop().time()
            duration = end_time - start_time
            sleep_time = max(0, BROADCAST_INTERVAL_SECONDS - duration)
            if duration > BROADCAST_INTERVAL_SECONDS:
                logger.warning(f"Broadcast loop took longer than interval: {duration:.3f}s")
            await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info("Plane update broadcast task cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in broadcast loop: {e}", exc_info=True)
            # Avoid busy-looping on persistent errors
            await asyncio.sleep(BROADCAST_INTERVAL_SECONDS * 2)

"""Background task for broadcasting plane state updates to connected clients."""

import asyncio
import logging
from typing import Dict, List

from pydantic import BaseModel, Field

from backend.ingest.main import PlaneState  # Assuming PlaneState is defined here

# Import the specific payload schema and WSMessage wrapper
from backend.schemas.ws import DeltaPayload, WSMessage
from backend.utils.connection_manager import ConnectionManager
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)

# How often to fetch and prepare updates (in seconds)
BROADCAST_INTERVAL_SECONDS = 1.0


# Define the structure for the delta update payload
class PlaneDeltaUpdate(BaseModel):
    updated: List[PlaneState] = Field(default_factory=list)
    removed: List[str] = Field(default_factory=list)  # List of hex_idents


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

    while True:
        try:
            start_time = asyncio.get_event_loop().time()

            # --- Task 42: Fetch Current Plane States ---
            current_planes_list: List[PlaneState] = []
            current_keys = set()
            # Get the underlying connection to use scan_iter
            conn = await redis_client.get_connection()
            async for key in conn.scan_iter("plane:*"):  # Use conn.scan_iter
                current_keys.add(key)
                try:
                    # Use get_model, not get_json, and provide the model type
                    plane = await redis_client.get_model(key, PlaneState)
                    if plane:
                        current_planes_list.append(plane)
                    # Remove the inner try/except for parsing, get_model handles it
                    # try:
                    #     plane = PlaneState(**plane_dict)
                    #     current_planes_list.append(plane)
                    # except Exception as parse_error:  # Catch Pydantic validation errors etc.
                    #     logger.warning(
                    #         f"Failed to parse PlaneState for key {key}: {parse_error}"
                    #     )
                    else:
                        # get_model returns None if key doesn't exist or fails parsing
                        logger.debug(f"Plane data not found or failed parse for key {key}.")
                except Exception as e:
                    logger.error(f"Error processing plane key {key}: {e}")

            current_state_map: Dict[str, PlaneState] = {p.hex_ident: p for p in current_planes_list}
            logger.debug(f"Fetched {len(current_state_map)} current plane states.")

            # --- Task 43: Calculate Delta --- #
            updated_planes: List[PlaneState] = []
            removed_plane_hexes: List[str] = []

            # Check for updated and new planes
            for hex_ident, current_plane in current_state_map.items():
                last_plane = last_state.get(hex_ident)
                # Add if new or if changed since last time
                # Using Pydantic's default __ne__ which compares model fields
                if last_plane is None or current_plane != last_plane:
                    updated_planes.append(current_plane)

            # Check for removed planes (present in last state but not current)
            removed_plane_hexes = [
                hex_ident for hex_ident in last_state if hex_ident not in current_state_map
            ]

            delta = PlaneDeltaUpdate(updated=updated_planes, removed=removed_plane_hexes)

            if delta.updated or delta.removed:
                logger.debug(
                    f"Delta calculated: {len(delta.updated)} updated, "
                    f"{len(delta.removed)} removed."
                )
            else:
                logger.debug("No changes detected in plane states.")

            # Update last_state for the next iteration
            last_state = current_state_map

            # --- Task 44: Broadcast Delta --- #
            if delta.updated or delta.removed:
                # Construct the actual WSMessage payload
                delta_payload_data = DeltaPayload(
                    planes=delta.model_dump()  # Use the PlaneDeltaUpdate structure
                )
                ws_message = WSMessage(type="delta", payload=delta_payload_data)

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
                            logger.debug(f"Delta broadcast successful to room '{room_code}'.")
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

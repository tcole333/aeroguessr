"""Plane filtering service for range-based and signal quality plane removal."""

import logging
import os
import time
from typing import Dict, List, Set

from backend.ingest.main import PlaneState
from backend.schemas.game import RoundData
from backend.utils.geo import haversine_km
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)

# Configuration from environment variables
CENTER_LAT = float(os.getenv("CENTER_LAT", "42.3656"))
CENTER_LON = float(os.getenv("CENTER_LON", "-71.0096"))
MAX_ANTENNA_RANGE_KM = float(os.getenv("MAX_ANTENNA_RANGE_KM", "250"))
MIN_UPDATE_INTERVAL_SECONDS = int(os.getenv("MIN_UPDATE_INTERVAL_SECONDS", "60"))

# Signal quality thresholds
MIN_UPDATES_FOR_QUALITY_CHECK = 3  # Minimum updates before applying quality filters
MIN_UPDATE_FREQUENCY_HZ = 1.0 / 30.0  # At least one update every 30 seconds


class PlaneFilter:
    """Service for filtering planes based on range and signal quality."""

    def __init__(self, redis_client: RedisClient) -> None:
        self.redis_client = redis_client
        self.antenna_pos = (CENTER_LAT, CENTER_LON)

    async def get_protected_planes(self) -> Set[str]:
        """Get list of plane hex IDs that should be protected from removal.

        This includes planes involved in active rounds across all rooms.

        Returns:
            Set of hex IDs that should not be removed
        """
        protected_planes = set()

        # Get all room codes by scanning room:*:meta keys
        cursor = 0
        async with await self.redis_client.get_connection() as conn:
            while True:
                cursor, keys = await conn.scan(cursor=cursor, match="room:*:meta", count=100)
                for key in keys:
                    key_str = key.decode() if isinstance(key, (bytes, bytearray)) else str(key)
                    room_code = key_str.split(":")[1]

                    # Check if this room has an active round
                    round_key = f"room:{room_code}:round"

                    # Use the wrapper method for consistency with codebase patterns
                    round_data = await self.redis_client.get_model(round_key, RoundData)

                    if round_data and round_data.selected_plane_hex:
                        protected_planes.add(round_data.selected_plane_hex)
                        hex_id = round_data.selected_plane_hex
                        logger.debug(f"Protected plane {hex_id} from room {room_code}")

                if cursor == 0:
                    break

        return protected_planes

    def is_plane_in_range(self, plane: PlaneState) -> bool:
        """Check if a plane is within the configured antenna range.

        Args:
            plane: PlaneState object to check

        Returns:
            True if plane is within range, False otherwise
        """
        distance_km = haversine_km(self.antenna_pos[0], self.antenna_pos[1], plane.lat, plane.lon)
        return distance_km <= MAX_ANTENNA_RANGE_KM

    def is_plane_recently_updated(self, plane: PlaneState) -> bool:
        """Check if a plane has been updated recently enough to be considered active.

        Args:
            plane: PlaneState object to check

        Returns:
            True if plane was updated recently, False otherwise
        """
        current_time = time.time()
        time_since_update = current_time - plane.last_update_ts
        return time_since_update <= MIN_UPDATE_INTERVAL_SECONDS

    def has_good_signal_quality(self, plane: PlaneState) -> bool:
        """Check if a plane has good signal quality based on update frequency.

        Args:
            plane: PlaneState object to check

        Returns:
            True if plane has good signal quality, False otherwise
        """
        # Skip quality check for new planes
        if plane.update_count < MIN_UPDATES_FOR_QUALITY_CHECK:
            return True

        current_time = time.time()
        time_tracking = current_time - plane.first_seen_ts

        # Avoid division by zero
        if time_tracking <= 0:
            return True

        # Calculate average update frequency
        avg_frequency = plane.update_count / time_tracking

        return avg_frequency >= MIN_UPDATE_FREQUENCY_HZ

    async def filter_stale_planes(self, planes: Dict[str, PlaneState]) -> List[str]:
        """Filter out planes that should be removed based on range and signal quality.

        Args:
            planes: Dictionary of hex_id -> PlaneState

        Returns:
            List of hex IDs that should be removed
        """
        protected_planes = await self.get_protected_planes()
        planes_to_remove = []

        for hex_id, plane in planes.items():
            # Never remove protected planes (in active rounds)
            if hex_id in protected_planes:
                logger.debug(f"Skipping protected plane {hex_id}")
                continue

            # Check if plane is out of range
            if not self.is_plane_in_range(plane):
                distance_km = haversine_km(
                    self.antenna_pos[0], self.antenna_pos[1], plane.lat, plane.lon
                )
                planes_to_remove.append(hex_id)
                logger.info(f"Removing plane {hex_id} - out of range ({distance_km:.1f}km)")
                continue

            # Check if plane hasn't been updated recently
            if not self.is_plane_recently_updated(plane):
                time_since_update = time.time() - plane.last_update_ts
                planes_to_remove.append(hex_id)
                logger.info(f"Removing plane {hex_id} - stale signal ({time_since_update:.0f}s)")
                continue

            # Check signal quality for established planes
            if not self.has_good_signal_quality(plane):
                avg_freq = plane.update_count / (time.time() - plane.first_seen_ts)
                planes_to_remove.append(hex_id)
                logger.info(f"Removing plane {hex_id} - poor signal quality ({avg_freq:.3f} Hz)")
                continue

        return planes_to_remove

    async def remove_planes_from_redis(self, hex_ids: List[str]) -> None:
        """Remove plane keys from Redis.

        Args:
            hex_ids: List of hex IDs to remove
        """
        if not hex_ids:
            return

        # Use the wrapper's delete method for consistency
        for hex_id in hex_ids:
            try:
                key = f"plane:{hex_id}"
                await self.redis_client.delete(key)
                logger.debug(f"Removed Redis key {key}")
            except Exception as e:
                logger.error(f"Failed to remove plane {hex_id}: {e}")

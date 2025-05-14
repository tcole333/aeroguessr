import asyncio
import logging
import time  # Import time for timestamps
from collections import defaultdict
from dataclasses import dataclass, field  # Import dataclasses
from typing import Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


@dataclass
class ConnectionState:
    """Holds the state for an active WebSocket connection, including heartbeat info."""

    websocket: WebSocket
    last_pong_received_ts: float = field(default_factory=time.time)
    missed_pings_count: int = 0
    # Optionally add: outstanding_ping_seq: Optional[int] = None


class ConnectionManager:
    """Manages active WebSocket connections and room-specific locks."""

    def __init__(self) -> None:
        """Initializes the connection manager."""
        # Structure: {room_code: {nickname: ConnectionState}}
        self.active_connections: Dict[str, Dict[str, ConnectionState]] = defaultdict(dict)
        # Lock management for room state modifications (e.g., guesses)
        self.room_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.active_tasks: Set[asyncio.Task] = set()
        logger.info("ConnectionManager initialized.")

    async def connect(self, websocket: WebSocket, room_code: str, nickname: str) -> None:
        """
        Registers a new WebSocket connection for a player in a room.

        Args:
            websocket: The WebSocket connection instance.
            room_code: The code of the room the player is joining.
            nickname: The nickname of the player joining.
        """
        await websocket.accept()
        # Store ConnectionState instead of just the WebSocket
        connection_state = ConnectionState(websocket=websocket)
        self.active_connections[room_code][nickname] = connection_state
        logger.info(f"Player '{nickname}' connected to room '{room_code}'.")

    def disconnect(self, room_code: str, nickname: str) -> None:
        """
        Removes a WebSocket connection and cleans up associated state.

        Args:
            room_code: The code of the room the player is leaving.
            nickname: The nickname of the player leaving.
        """
        if room_code in self.active_connections and nickname in self.active_connections[room_code]:
            # Optional: Log connection details before removal if needed
            # connection_state = self.active_connections[room_code][nickname]
            # logger.debug(f"Disconnecting state: {connection_state}")
            del self.active_connections[room_code][nickname]
            # Clean up room if empty
            if not self.active_connections[room_code]:
                del self.active_connections[room_code]
                # Clean up lock if room becomes empty
                if room_code in self.room_locks:
                    del self.room_locks[room_code]
                    logger.debug(f"Cleaned up lock for empty room '{room_code}'.")
            logger.info(f"Player '{nickname}' disconnected from room '{room_code}'.")
        else:
            logger.warning(
                f"Attempted to disconnect non-existent player '{nickname}' from room '{room_code}'."
            )

    def get_connection_state(self, room_code: str, nickname: str) -> Optional[ConnectionState]:
        """Retrieves the ConnectionState for a specific player, if they exist."""
        return self.active_connections.get(room_code, {}).get(nickname)

    def get_room_connections(self, room_code: str) -> Dict[str, ConnectionState]:
        """Returns the dictionary of connection states for a specific room."""
        return self.active_connections.get(room_code, {})

    def get_room_lock(self, room_code: str) -> asyncio.Lock:
        """Returns the asyncio.Lock associated with the given room code."""
        # defaultdict ensures lock is created on first access for a room
        return self.room_locks[room_code]

    def record_pong(self, room_code: str, nickname: str) -> bool:
        """
        Records that a pong was received from a player, resetting missed count.

        Args:
            room_code: The room the player is in.
            nickname: The player's nickname.

        Returns:
            True if the player was found and updated, False otherwise.
        """
        connection_state = self.get_connection_state(room_code, nickname)
        if connection_state:
            connection_state.last_pong_received_ts = time.time()
            connection_state.missed_pings_count = 0
            logger.debug(f"Recorded pong for {nickname} in {room_code}.")
            return True
        else:
            logger.warning(
                f"Could not record pong for non-existent player {nickname} in {room_code}."
            )
            return False

    def increment_missed_ping(self, room_code: str, nickname: str) -> Optional[int]:
        """
        Increments the missed ping counter for a player.

        Args:
            room_code: The room the player is in.
            nickname: The player's nickname.

        Returns:
            The new missed ping count if the player exists, otherwise None.
        """
        connection_state = self.get_connection_state(room_code, nickname)
        if connection_state:
            connection_state.missed_pings_count += 1
            logger.debug(
                f"Incremented missed pings for {nickname} in {room_code} to "
                f"{connection_state.missed_pings_count}."
            )
            return connection_state.missed_pings_count
        else:
            logger.warning(
                f"Could not increment missed ping for non-existent player {nickname} "
                f"in {room_code}."
            )
            return None

    def add_task(self, task: asyncio.Task) -> None:
        """Adds a task to the active_tasks set for tracking."""
        self.active_tasks.add(task)
        logger.debug(f"Task {task.get_name()} added to active_tasks set.")

    def _remove_task_from_set(self, task: asyncio.Task) -> None:
        """Callback to remove a task from the active_tasks set when it's done."""
        self.active_tasks.discard(task)
        logger.debug(f"Task {task.get_name()} removed from active_tasks set via callback.")

    async def send_personal_message(self, message: dict, websocket: WebSocket) -> None:
        """
        Sends a JSON message to a specific WebSocket connection.

        Args:
            message: The message payload (dictionary) to send.
            websocket: The target WebSocket connection.

        Raises:
            WebSocketDisconnect: If the send operation fails because the socket is closed.
        """
        try:
            await websocket.send_json(message)
            logger.debug(f"Sent personal message to {websocket.client}: {message.get('type')}")
        except WebSocketDisconnect:
            logger.warning(f"Failed to send personal message to {websocket.client}: disconnected.")
            raise  # Re-raise to allow caller to handle disconnection
        except RuntimeError as e:
            # websockets library can raise RuntimeError if connection closed unexpectedly
            if "Connection closed" in str(e):
                logger.warning(f"Failed to send personal message to {websocket.client}: {e}")
                raise WebSocketDisconnect from e
            else:
                logger.error(f"Unexpected runtime error sending to {websocket.client}: {e}")
                raise

    async def broadcast(
        self, message: dict, room_code: str, exclude_nickname: Optional[str] = None
    ) -> None:
        """
        Broadcasts a JSON message to all connected clients in a specific room.

        Args:
            message: The message payload (dictionary) to send.
            room_code: The target room code.
            exclude_nickname: An optional nickname to exclude from the broadcast.
        """
        disconnected_players = []
        room_connection_states = self.get_room_connections(room_code)

        if not room_connection_states:
            # Log only if the room was expected to exist (i.e., if active_connections had the key)
            if room_code in self.active_connections:
                logger.warning(f"Attempted to broadcast to empty room '{room_code}'.")
            # else: room likely already cleaned up, no warning needed.
            return

        logger.debug(
            f"Broadcasting message type '{message.get('type')}' to room "
            f"'{room_code}' (excluding {exclude_nickname})..."
        )

        for nickname, connection_state in room_connection_states.items():
            if nickname == exclude_nickname:
                continue
            try:
                # Extract websocket from ConnectionState
                await self.send_personal_message(message, connection_state.websocket)
            except WebSocketDisconnect:
                # Mark for disconnection, don't modify dict during iteration
                disconnected_players.append(nickname)
            except Exception as e:
                logger.error(
                    f"Unexpected error broadcasting to {nickname} in room {room_code}: {e}"
                )

        # Clean up disconnected players after iteration
        for nickname in disconnected_players:
            logger.info(
                f"Removing disconnected player '{nickname}' from room '{room_code}' "
                "during broadcast."
            )
            self.disconnect(room_code, nickname)  # Handles logging and potential room cleanup

import logging
from collections import defaultdict
from typing import Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections for game rooms."""

    def __init__(self) -> None:
        """Initializes the connection manager."""
        # Structure: {room_code: {nickname: WebSocket}}
        self.active_connections: Dict[str, Dict[str, WebSocket]] = defaultdict(dict)
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
        self.active_connections[room_code][nickname] = websocket
        logger.info(f"Player '{nickname}' connected to room '{room_code}'.")

    def disconnect(self, room_code: str, nickname: str) -> None:
        """
        Removes a WebSocket connection.

        Args:
            room_code: The code of the room the player is leaving.
            nickname: The nickname of the player leaving.
        """
        if room_code in self.active_connections and nickname in self.active_connections[room_code]:
            del self.active_connections[room_code][nickname]
            # Clean up room if empty
            if not self.active_connections[room_code]:
                del self.active_connections[room_code]
            logger.info(f"Player '{nickname}' disconnected from room '{room_code}'.")
        else:
            logger.warning(
                f"Attempted to disconnect non-existent player '{nickname}' from room '{room_code}'."
            )

    def get_room_connections(self, room_code: str) -> Dict[str, WebSocket]:
        """Returns the dictionary of connections for a specific room."""
        return self.active_connections.get(room_code, {})

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
        if room_code not in self.active_connections:
            logger.warning(f"Attempted to broadcast to non-existent room '{room_code}'.")
            return

        room_connections = self.active_connections[room_code]
        logger.debug(
            f"Broadcasting message type '{message.get('type')}' to room "
            f"'{room_code}' (excluding {exclude_nickname})..."
        )

        for nickname, connection in room_connections.items():
            if nickname == exclude_nickname:
                continue
            try:
                await self.send_personal_message(message, connection)
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

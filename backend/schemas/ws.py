import time  # Needed for timestamp in WSMessage
from typing import Dict, List

from pydantic import BaseModel, Field

# Attempt to import core schemas, handle potential circularity if needed later
try:
    from .core import Player, RoomMeta
except ImportError:
    # Placeholder if core.py isn't available or for type checking contexts
    # This might indicate a need to restructure schemas later
    Player = Dict  # type: ignore
    RoomMeta = Dict  # type: ignore


# Define base structure for WS messages (as per PRD)
class WSMessage(BaseModel):
    type: str = Field(..., description="The type of the WebSocket message.")
    # Allow flexible payload types
    payload: Dict | List | BaseModel | None = Field(..., description="The message payload.")
    ts: float = Field(
        default_factory=lambda: time.time() * 1000,
        description="Timestamp (epoch milliseconds) when the message was generated.",
    )


# Define payload for stateSync
class FullRoomState(BaseModel):
    """Represents the complete state of a room to be sent on connect."""

    room_meta: RoomMeta | None = Field(description="Current metadata of the room.")
    players: Dict[str, Player] = Field(
        description="Dictionary of players currently in the room, keyed by nickname."
    )
    # Add other state elements as needed, e.g., current round info

    class Config:
        """Pydantic configuration."""

        # Add example based on actual or placeholder types
        json_schema_extra = {
            "example": {
                "room_meta": {  # Example RoomMeta structure
                    "mode": "Distance",
                    "round_timeout_seconds": 45,
                    "host_nickname": "HostHarry",
                    "created_ts": 1678886400.0,
                }
                if isinstance(RoomMeta, type)
                else None,
                "players": {  # Example Players structure
                    "HostHarry": {
                        "nickname": "HostHarry",
                        "score": 100,
                        "connected": True,
                        "last_seen_ts": 1678886401.0,
                    },
                    "JoinerJane": {
                        "nickname": "JoinerJane",
                        "score": 50,
                        "connected": True,
                        "last_seen_ts": 1678886402.0,
                    },
                }
                if isinstance(Player, type)
                else {},
            }
        }


# We will add schemas for other WS message types here (e.g., delta, roundStart)

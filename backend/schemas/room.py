import random
import string
import time
from typing import Dict, Optional

from pydantic import BaseModel, Field

from .core import Player, RoomMeta, ScoringMode
from .game import RoundData


def generate_room_code(length: int = 4) -> str:
    """Generates a random room code."""
    return "".join(random.choices(string.ascii_uppercase, k=length))


class RoomCreateRequest(BaseModel):
    """Request body for creating a new game room."""

    host_nickname: str = Field(
        ..., min_length=3, max_length=30, description="Nickname for the player hosting the room."
    )
    mode: ScoringMode = Field(default=ScoringMode.EXACT, description="Scoring mode for the room.")
    round_timeout_seconds: int = Field(
        default=30, ge=10, le=120, description="Duration of each guessing round in seconds."
    )

    class Config:
        """Pydantic configuration."""

        use_enum_values = True
        json_schema_extra = {
            "example": {
                "host_nickname": "HostessHannah",
                "mode": "Distance",
                "round_timeout_seconds": 60,
            }
        }


class RoomCreateResponse(BaseModel):
    """Response body after successfully creating a game room."""

    room_code: str = Field(..., description="The unique 4-letter code for the created room.")
    ws_url: str = Field(..., description="The WebSocket URL for the host to connect to.")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "room_code": "ABCD",
                "ws_url": "ws://localhost:8000/ws/ABCD/HostessHannah",  # Example URL
            }
        }


# We might add more room-related schemas here later, e.g., for joining.


class RoomJoinRequest(BaseModel):
    """Request body for joining an existing game room."""

    nickname: str = Field(
        ..., min_length=3, max_length=30, description="Nickname for the player joining the room."
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "nickname": "JoinerJane",
            }
        }


class RoomJoinResponse(BaseModel):
    """Response body after successfully joining a game room."""

    ws_url: str = Field(..., description="The WebSocket URL for the player to connect to.")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "ws_url": "ws://localhost:8000/ws/WXYZ/JoinerJane"  # Example URL
            }
        }


# ---- New Schema ----
class RoomState(RoomMeta):
    """Represents the complete state of a game room, suitable for debug view or state sync."""

    code: str = Field(..., description="The 4-letter code identifying the room.")
    players: Dict[str, Player] = Field(
        default_factory=dict, description="Players currently in the room, keyed by nickname."
    )
    current_round: Optional[RoundData] = Field(
        default=None, description="Data for the currently active round, if any."
    )

    class Config(RoomMeta.Config):
        """Pydantic configuration, inherits from RoomMeta."""

        json_schema_extra = {
            "example": {
                # Inherited from RoomMeta example
                "mode": "Distance",
                "round_timeout_seconds": 45,
                "host_nickname": "HostHarry",
                "created_ts": time.time(),
                # RoomState specific fields
                "code": "WXYZ",
                "players": {
                    "HostHarry": {
                        "nickname": "HostHarry",
                        "score": 100,
                        "connected": True,
                        "last_seen_ts": time.time(),
                    },
                    "JoinerJane": {
                        "nickname": "JoinerJane",
                        "score": 50,
                        "connected": True,
                        "last_seen_ts": time.time() - 10,
                    },
                },
                "current_round": {  # Example using RoundData's example
                    "state": "accepting_guesses",
                    "selected_plane_hex": "a1b2c3",
                    "correct_airport_code": "JFK",
                    "guess_direction": "destination",
                    "round_start_time": time.time() - 10,
                    "guesses": {
                        "JoinerJane": {
                            "nickname": "JoinerJane",
                            "guess": "LGA",
                            "timestamp": time.time() - 5,
                        }
                    },
                    "results": None,
                    "round_number": 3,
                },
            }
        }

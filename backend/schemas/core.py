import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ScoringMode(str, Enum):
    """Enum for available scoring modes."""

    EXACT = "Exact"
    DISTANCE = "Distance"


class Player(BaseModel):
    """Represents a player within a game room."""

    nickname: str = Field(..., description="Unique nickname chosen by the player.")
    score: int = Field(default=0, description="Player's current score.")
    connected: bool = Field(
        default=False, description="Whether the player is currently connected via WebSocket."
    )
    last_seen_ts: float | None = Field(
        default=None, description="Timestamp of the last activity or connection."
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "nickname": "PilotPete",
                "score": 150,
                "connected": True,
                "last_seen_ts": 1678886401.0,
            }
        }


class RoomMeta(BaseModel):
    """Metadata about a game room stored in Redis."""

    mode: ScoringMode = Field(..., description="Scoring mode for the room.")
    round_timeout_seconds: int = Field(..., description="Duration of each guessing round.")
    host_nickname: str = Field(..., description="Nickname of the current host.")
    is_solo: bool = Field(
        default=False,
        description="Whether this room represents a solo game session.",
    )
    created_ts: float = Field(
        default_factory=time.time, description="Timestamp when the room was created."
    )
    host_disconnected_ts: Optional[float] = Field(
        default=None, description="Timestamp when the host disconnected, None if connected."
    )

    class Config:
        """Pydantic configuration."""

        use_enum_values = True  # Store enum values as strings
        json_schema_extra = {
            "example": {
                "mode": "Exact",
                "round_timeout_seconds": 30,
                "host_nickname": "PlayerOne",
                "is_solo": False,
                "created_ts": 1678886400.0,
                "host_disconnected_ts": None,
            }
        }

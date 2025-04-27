import time
from enum import Enum

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
                "last_seen_ts": time.time(),
            }
        }


class RoomMeta(BaseModel):
    """Metadata associated with a game room."""

    mode: ScoringMode = Field(default=ScoringMode.EXACT, description="Scoring mode for the room.")
    round_timeout_seconds: int = Field(
        default=30, ge=10, le=120, description="Duration of each guessing round in seconds."
    )
    host_nickname: str = Field(
        ..., description="Nickname of the player currently hosting the room."
    )
    created_ts: float = Field(
        default_factory=time.time, description="Timestamp when the room was created."
    )
    # Room code itself is typically the key in Redis, not stored within the metadata value.

    class Config:
        """Pydantic configuration."""

        use_enum_values = True  # Store enum values as strings
        json_schema_extra = {
            "example": {
                "mode": "Distance",
                "round_timeout_seconds": 45,
                "host_nickname": "HostHarry",
                "created_ts": time.time(),
            }
        }


# Note: The Plane model is more complex and related to ingest;
# we'll likely define it separately, possibly in schemas/plane.py later.

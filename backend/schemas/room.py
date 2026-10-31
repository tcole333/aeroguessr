import secrets
import string

from pydantic import BaseModel, Field

from .core import ScoringMode


def generate_room_code(length: int = 4) -> str:
    """Generates a random room code. The code is what lets a player join, so it uses secrets."""
    return "".join(secrets.choice(string.ascii_uppercase) for _ in range(length))


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
                "ws_url": "ws://localhost:8000/api/v0/rooms/ws/ABCD/HostessHannah",
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

    room_code: str = Field(..., description="Room code assigned for the joined session.")
    ws_url: str = Field(..., description="The WebSocket URL for the player to connect to.")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "room_code": "ABCD",
                "ws_url": "ws://localhost:8000/api/v0/rooms/ws/ABCD/JoinerJane",
            }
        }

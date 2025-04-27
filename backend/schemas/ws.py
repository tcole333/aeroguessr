import time  # Needed for timestamp in WSMessage
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# Attempt to import core schemas, handle potential circularity if needed later
try:
    from .core import Player, RoomMeta
    from .game import RoundResultDetail
except ImportError:
    # Placeholder if core.py isn't available or for type checking contexts
    # This might indicate a need to restructure schemas later
    Player = Dict  # type: ignore
    RoomMeta = Dict  # type: ignore


class PingPongPayload(BaseModel):
    """Payload for ping and pong messages."""

    seq: int = Field(..., description="Sequence number for matching ping/pong.")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {"example": {"seq": 12345}}


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


# --- Payloads for Player Events --- #


class PlayerJoinedPayload(BaseModel):
    """Payload for the playerJoined message."""

    nickname: str = Field(..., description="Nickname of the player who joined.")
    # You might add the full Player object later if needed

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {"example": {"nickname": "NewPlayer123"}}


class PlayerLeftPayload(BaseModel):
    """Payload for the playerLeft message."""

    nickname: str = Field(..., description="Nickname of the player who left.")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {"example": {"nickname": "LeavingPlayer456"}}


# --- Game Logic Payloads --- #


class SelectPlanePayload(BaseModel):
    """Payload for the host selectPlane message."""

    hex: str = Field(..., description="ICAO24 hex code of the selected plane.")

    class Config:
        json_schema_extra = {"example": {"hex": "a1b2c3"}}


class StartRoundPayload(BaseModel):
    """Payload for the host startRound message (currently empty)."""

    # No payload needed currently, but define for structure
    pass


class GuessPayload(BaseModel):
    """Payload for the player guess message."""

    airport_code: str = Field(..., description="Player's guessed airport IATA/ICAO code.")

    class Config:
        json_schema_extra = {"example": {"airport_code": "JFK"}}


class RoundStartPayload(BaseModel):
    """Payload for the server roundStart message."""

    hex: str = Field(..., description="ICAO24 hex code of the plane for this round.")
    timeout_s: int = Field(..., description="Duration of the guessing round in seconds.")
    direction: str = Field(..., description="Whether to guess 'origin' or 'destination'.")
    round_number: int = Field(..., description="The current round number.")

    class Config:
        json_schema_extra = {
            "example": {
                "hex": "a1b2c3",
                "timeout_s": 30,
                "direction": "destination",
                "round_number": 4,
            }
        }


class RoundResultPayload(BaseModel):
    """Payload for the server roundResult message."""

    results: List[RoundResultDetail] = Field(
        ..., description="List containing results for each player."
    )
    next_host_nickname: Optional[str] = Field(
        default=None,
        description="Nickname of the player who will host the next round (if changed).",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "results": [
                    {
                        "nickname": "Player1",
                        "guess": "JFK",
                        "correct_code": "BOS",
                        "score_awarded": 0,
                        "current_total_score": 150,
                    },
                    {
                        "nickname": "Player2",
                        "guess": "BOS",
                        "correct_code": "BOS",
                        "score_awarded": 100,
                        "current_total_score": 200,
                    },
                ],
                "next_host_nickname": None,
            }
        }


class NewHostPayload(BaseModel):
    """Payload for the server newHost message."""

    nickname: str = Field(..., description="Nickname of the new host.")

    class Config:
        json_schema_extra = {"example": {"nickname": "PromotedPlayer"}}


class TransferHostPayload(BaseModel):
    """Payload for the host transferHost message."""

    to_nickname: str = Field(..., description="Nickname of the player to transfer host to.")

    class Config:
        json_schema_extra = {"example": {"to_nickname": "SuccessorSam"}}


class ClaimHostPayload(BaseModel):
    """Payload for the player claimHost message (currently empty)."""

    # No payload needed currently
    pass


class PlaneSelectedConfirmPayload(BaseModel):
    """Payload sent to host confirming successful plane selection."""

    hex: str = Field(..., description="ICAO24 hex code of the selected plane.")
    origin: str = Field(..., description="Origin airport ICAO code.")
    destination: str = Field(..., description="Destination airport ICAO code.")
    guess_direction: str = Field(
        ..., description="Which airport players will guess ('origin' or 'destination')."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "hex": "a1b2c3",
                "origin": "KBOS",
                "destination": "KJFK",
                "guess_direction": "destination",
            }
        }


class ErrorPayload(BaseModel):
    """Payload for the server error message."""

    code: str = Field(..., description="Short error code (e.g., 'INVALID_STATE').")
    message: str = Field(..., description="User-friendly error message.")

    class Config:
        json_schema_extra = {
            "example": {
                "code": "GUESS_OUTSIDE_ROUND",
                "message": "Guesses only allowed during round.",
            }
        }


# --- Wrapper Message --- #

# Example of creating ping/pong messages:
# ping_msg = WSMessage(type="ping", payload=PingPongPayload(seq=1))
# pong_msg = WSMessage(type="pong", payload=PingPongPayload(seq=1))

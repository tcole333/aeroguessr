import time  # Needed for timestamp in WSMessage
from enum import Enum  # Import Enum
from typing import Annotated, Dict, List, Optional

from pydantic import BaseModel, Field, StringConstraints

from backend.schemas.core import Player, RoomMeta
from backend.schemas.game import RoundResultDetail
from backend.schemas.plane import GuessDirection, PublicPlaneState

# --- Error Codes Enum --- #


class ErrorCode(str, Enum):
    """Standardized error codes for WebSocket error messages."""

    # Generic
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    INVALID_MESSAGE_FORMAT = "INVALID_MESSAGE_FORMAT"
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"

    # Room / Connection
    ROOM_NOT_FOUND = "ROOM_NOT_FOUND"
    NICKNAME_TAKEN = "NICKNAME_TAKEN"
    NOT_IN_ROOM = "NOT_IN_ROOM"

    # Host Actions
    NOT_HOST = "NOT_HOST"
    PLAYER_NOT_FOUND = "PLAYER_NOT_FOUND"
    CANNOT_TRANSFER_TO_SELF = "CANNOT_TRANSFER_TO_SELF"

    # Claim Host Flow
    CLAIM_HOST_NOT_ALLOWED = "CLAIM_HOST_NOT_ALLOWED"  # Generic fallback
    CLAIM_HOST_STILL_CONNECTED = "CLAIM_HOST_STILL_CONNECTED"  # Host reconnected
    CLAIM_HOST_TOO_EARLY = "CLAIM_HOST_TOO_EARLY"  # Claim window not open yet

    # Game Flow
    INVALID_STATE_FOR_ACTION = "INVALID_STATE_FOR_ACTION"
    PLANE_NOT_FOUND = "PLANE_NOT_FOUND"
    PLANE_ALREADY_USED = "PLANE_ALREADY_USED"
    INVALID_PLANE_SELECTION = "INVALID_PLANE_SELECTION"
    GUESS_OUTSIDE_ROUND = "GUESS_OUTSIDE_ROUND"
    ALREADY_GUESSED = "ALREADY_GUESSED"
    INVALID_ACTION_IN_SOLO_MODE = "INVALID_ACTION_IN_SOLO_MODE"
    PLANE_DATA_INCOMPLETE_FOR_GUESS = "PLANE_DATA_INCOMPLETE_FOR_GUESS"
    UNKNOWN_AIRPORT_CODE = "UNKNOWN_AIRPORT_CODE"  # Guess is not in the airport dataset


# --- Base Message & Common Payloads --- #


# Add PingPongPayload back
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
    payload: Dict | List | PingPongPayload | BaseModel | None = Field(
        ..., description="The message payload."
    )
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

        json_schema_extra = {
            "example": {
                "room_meta": {
                    "mode": "Distance",
                    "round_timeout_seconds": 45,
                    "host_nickname": "HostHarry",
                    "is_solo": False,
                    "created_ts": 1678886400.0,
                    "host_disconnected_ts": None,
                },
                "players": {
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
                },
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


class SkipRoundPayload(BaseModel):
    """Payload for the host skipRound message (currently empty)."""

    # No payload fields required
    pass


# Every IATA/ICAO code in data/airports.json is 3-8 characters (IATA is 3, most
# ICAO idents are 4, the longest is 8); anything outside that can't be a guess.
GuessAirportCode = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=3, max_length=8)
]


class GuessPayload(BaseModel):
    """Payload for the player guess message."""

    airport_code: GuessAirportCode = Field(
        ..., description="Player's guessed airport IATA/ICAO code (trimmed and uppercased)."
    )

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
    hex: Optional[str] = Field(
        default=None,
        description=(
            "ICAO24 hex code of the plane this round was about. With results[].correct_code "
            "this is the only message that reveals the plane's answer airport."
        ),
    )

    class Config:
        json_schema_extra = {
            "example": {
                "hex": "a1b2c3",
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

    # No payload needed currently, server identifies sender via connection
    pass


class LeavePayload(BaseModel):
    """Payload for the player leave message (currently empty)."""

    # No payload needed currently, server identifies sender via connection
    pass


class PlaneSelectedConfirmPayload(BaseModel):
    """Payload confirming a plane selection to its host or solo player; it names no airport."""

    hex: str = Field(..., description="ICAO24 hex code of the selected plane.")
    guess_direction: GuessDirection = Field(
        ..., description="Which airport players will guess ('origin' or 'destination')."
    )

    class Config:
        json_schema_extra = {"example": {"hex": "a1b2c3", "guess_direction": "destination"}}


class ErrorPayload(BaseModel):
    """Payload for the server error message."""

    code: ErrorCode = Field(..., description="Standardized error code.")  # Use Enum
    message: str = Field(..., description="User-friendly error message.")

    class Config:
        json_schema_extra = {
            "example": {
                "code": "GUESS_OUTSIDE_ROUND",
                "message": "Guesses only allowed during round.",
            }
        }


# --- Delta Update Payload --- #


class RoundDelta(BaseModel):
    """Partial round state update for delta messages."""

    state: str = Field(..., description="Current round state.")
    round_number: int = Field(..., description="Round counter after the update.")


class DeltaPayload(BaseModel):
    """Payload for the server delta message, containing state changes."""

    planes: Optional[Dict[str, List[PublicPlaneState | str]]] = Field(
        default=None,
        description=(
            "Changes in plane states. 'updated' contains PublicPlaneState objects, "
            "'removed' contains hex IDs."
        ),
    )
    scores: Optional[Dict[str, int]] = Field(
        default=None, description="Updated scores for players {nickname: new_total_score}."
    )
    round: Optional["RoundDelta"] = Field(
        default=None,
        description="Updated round state information.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "planes": {
                    "updated": [
                        {
                            "hex_ident": "a1b2c3",
                            "lat": 42.36,
                            "lon": -71.05,
                            "alt": 5000,
                            "lat_v": 0.01,
                            "lon_v": -0.01,
                            "alt_v": -700.0,
                            "last_update_ts": 1700000000000.0,
                            "trail": [[42.359, -71.049, 4990]],
                            "callsign": "UAL123",
                            "operator": "United",
                            "first_seen_ts": 1700000000.0,
                            "update_count": 12,
                            "route_hint": {
                                "guess_direction": "destination",
                                "known_airport": "KBOS",
                                "eligible": True,
                            },
                        }
                    ],
                    "removed": ["d4e5f6"],
                },
                "scores": {"Player1": 250},
                "round": {"state": "waiting_for_selection", "round_number": 2},
            }
        }


# --- Message Type Enum --- #


# Define an Enum for message types for better control and validation
class WSMessageType(str, Enum):
    """Enumeration of WebSocket message types."""

    # Client -> Server
    PING = "ping"  # Added
    GUESS = "guess"
    SELECT_PLANE = "selectPlane"
    START_ROUND = "startRound"  # Host command
    SKIP_ROUND = "skipRound"  # Host command
    TRANSFER_HOST = "transferHost"  # Host command
    CLAIM_HOST = "claimHost"  # Player command
    LEAVE = "leave"

    # Server -> Client
    PONG = "pong"  # Added
    STATE_SYNC = "stateSync"  # Initial state or reconnect
    DELTA = "delta"  # Incremental state updates (planes, scores)
    ROUND_START = "roundStart"
    ROUND_RESULT = "roundResult"
    PLAYER_JOINED = "playerJoined"
    PLAYER_LEFT = "playerLeft"
    NEW_HOST = "newHost"
    PLANE_SELECTED_CONFIRM = "planeSelectedConfirm"  # Confirmation to host
    ERROR = "error"


# --- Type Hint for Specific Message Payloads --- #

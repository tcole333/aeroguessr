import time
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# Placeholder type for airport codes
AirportCode = str


class SoloSelectionContext(BaseModel):
    """State for a solo player's current selection."""

    selected_plane_hex: Optional[str] = Field(
        default=None, description="ICAO hex code of the player's selected plane."
    )
    correct_airport_code: Optional[AirportCode] = Field(
        default=None, description="The airport code considered correct for scoring."
    )
    guess_direction: Optional[str] = Field(
        default=None, description="Whether the guess should be for origin or destination."
    )


class RoundStateEnum(str, Enum):
    """Possible states for a game round."""

    WAITING_FOR_SELECTION = "waiting_for_selection"  # Host needs to select a plane
    ACCEPTING_GUESSES = "accepting_guesses"  # Round is active, players can guess
    SHOWING_RESULTS = "showing_results"  # Round ended, displaying scores


class PlayerGuess(BaseModel):
    """Stores a player's guess for a round."""

    nickname: str
    guess: AirportCode
    timestamp: float = Field(default_factory=time.time)


class RoundResultDetail(BaseModel):
    """Detailed result for a single player in a round."""

    nickname: str
    guess: AirportCode | None  # None if player didn't guess
    correct_code: AirportCode
    score_awarded: int
    current_total_score: int
    distance_km: Optional[float] = Field(
        default=None,
        description="Distance in km between guess and correct answer (Distance mode only)",
    )


class RoundData(BaseModel):
    """Data stored in Redis for the current state of a game round (`room:{code}:round`)."""

    state: RoundStateEnum = Field(
        default=RoundStateEnum.WAITING_FOR_SELECTION, description="The current phase of the round."
    )
    selected_plane_hex: Optional[str] = Field(
        default=None, description="ICAO hex code of the plane selected for this round."
    )
    correct_airport_code: Optional[AirportCode] = Field(
        default=None,
        description="The correct origin/destination airport code for the selected plane.",
    )
    guess_direction: Optional[str] = Field(
        default=None, description="Whether players are guessing 'origin' or 'destination'."
    )
    round_start_time: Optional[float] = Field(
        default=None, description="Timestamp when the guessing period started."
    )
    guesses: Dict[str, PlayerGuess] = Field(
        default_factory=dict, description="Guesses submitted by players {nickname: PlayerGuess}."
    )
    results: Optional[List[RoundResultDetail]] = Field(
        default=None, description="Scoring results after the round ends."
    )
    round_number: int = Field(default=0, description="Counter for the current round number.")

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "state": "accepting_guesses",
                "selected_plane_hex": "a1b2c3",
                "correct_airport_code": "JFK",
                "guess_direction": "destination",
                "round_start_time": time.time() - 10,
                "guesses": {
                    "PilotPete": {
                        "nickname": "PilotPete",
                        "guess": "LGA",
                        "timestamp": time.time() - 5,
                    }
                },
                "results": None,
                "round_number": 3,
            }
        }

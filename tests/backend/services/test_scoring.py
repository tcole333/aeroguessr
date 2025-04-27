"""Unit tests for the scoring service."""

from unittest.mock import MagicMock, patch

import pytest

from backend.services import scoring

# Test data
MOCK_AIRPORTS = {
    "BOS": (42.3656, -71.0096),  # Boston Logan
    "JFK": (40.6413, -73.7781),  # JFK New York (Approx 305km)
    "PVD": (41.7234, -71.4381),  # Providence (Approx 70km)
    "FAR": (46.9207, -96.8163),  # Fargo (Approx 2150km > 1000km)
}

# --- calculate_exact_score Tests --- #


@pytest.mark.parametrize(
    "correct, guessed, expected_score",
    [
        ("BOS", "BOS", 100),
        ("BOS", "bos", 100),  # Case-insensitive
        ("JFK", "BOS", 0),
        ("LHR", "lhr", 100),
        ("", "", 100),  # Empty strings match
        ("BOS", "", 0),
    ],
)
def test_calculate_exact_score(correct: str, guessed: str, expected_score: int) -> None:
    """Test exact score calculation."""
    assert scoring.calculate_exact_score(correct, guessed) == expected_score


# --- calculate_distance_score Tests --- #


# Patch the coordinate lookup within the test scope
@patch(
    "backend.services.scoring.get_airport_coords",
    side_effect=lambda code: MOCK_AIRPORTS.get(code.upper()),
)
def test_calculate_distance_score_exact_match(mock_get_coords: MagicMock) -> None:
    """Test distance score when guess is exactly correct."""
    assert scoring.calculate_distance_score("BOS", "BOS") == 100
    mock_get_coords.assert_called()


@patch(
    "backend.services.scoring.get_airport_coords",
    side_effect=lambda code: MOCK_AIRPORTS.get(code.upper()),
)
@patch("backend.services.scoring.calculate_distance_km")  # Mock the actual distance calc
def test_calculate_distance_score_close_guess(
    mock_calc_dist: MagicMock, mock_get_coords: MagicMock
) -> None:
    """Test distance score for a close guess (< 1000 km)."""
    # Mock distance for BOS <-> PVD to be 70km
    mock_calc_dist.return_value = 70.0
    # Score = max(0, 100 - 70 / 10) = max(0, 100 - 7) = 93
    assert scoring.calculate_distance_score("BOS", "PVD") == 93
    # Ensure coords were looked up and distance calculated
    assert mock_get_coords.call_count == 2
    mock_calc_dist.assert_called_once_with(MOCK_AIRPORTS["BOS"], MOCK_AIRPORTS["PVD"])


@patch(
    "backend.services.scoring.get_airport_coords",
    side_effect=lambda code: MOCK_AIRPORTS.get(code.upper()),
)
@patch("backend.services.scoring.calculate_distance_km")
def test_calculate_distance_score_far_guess(
    mock_calc_dist: MagicMock, mock_get_coords: MagicMock
) -> None:
    """Test distance score for a far guess (> 1000 km)."""
    # Mock distance for BOS <-> FAR to be 2150km
    mock_calc_dist.return_value = 2150.0
    # Score = max(0, 100 - 2150 / 10) = max(0, 100 - 215) = 0
    assert scoring.calculate_distance_score("BOS", "FAR") == 0
    assert mock_get_coords.call_count == 2
    mock_calc_dist.assert_called_once_with(MOCK_AIRPORTS["BOS"], MOCK_AIRPORTS["FAR"])


@patch(
    "backend.services.scoring.get_airport_coords",
    side_effect=lambda code: MOCK_AIRPORTS.get(code.upper()),
)
@patch("backend.services.scoring.calculate_distance_km")
def test_calculate_distance_score_invalid_guess(
    mock_calc_dist: MagicMock, mock_get_coords: MagicMock
) -> None:
    """Test distance score when the guessed airport code is invalid."""
    assert scoring.calculate_distance_score("BOS", "INVALID") == 0
    # Ensure correct airport was looked up, but invalid wasn't found
    mock_get_coords.assert_any_call("BOS")
    mock_get_coords.assert_any_call("INVALID")
    # Distance calculation should not be called if coords are missing
    mock_calc_dist.assert_not_called()


@patch(
    "backend.services.scoring.get_airport_coords",
    side_effect=lambda code: MOCK_AIRPORTS.get(code.upper()),
)
@patch("backend.services.scoring.calculate_distance_km", return_value=1000.0)
def test_calculate_distance_score_boundary(
    mock_calc_dist: MagicMock, mock_get_coords: MagicMock
) -> None:
    """Test distance score at the 1000km boundary."""
    # Score = max(0, 100 - 1000 / 10) = max(0, 100 - 100) = 0
    assert (
        scoring.calculate_distance_score("BOS", "JFK") == 0
    )  # Using JFK coords, but mocked distance
    mock_calc_dist.assert_called_once_with(MOCK_AIRPORTS["BOS"], MOCK_AIRPORTS["JFK"])


@patch(
    "backend.services.scoring.get_airport_coords",
    side_effect=lambda code: MOCK_AIRPORTS.get(code.upper()),
)
@patch("backend.services.scoring.calculate_distance_km", return_value=999.9)
def test_calculate_distance_score_just_below_boundary(
    mock_calc_dist: MagicMock, mock_get_coords: MagicMock
) -> None:
    """Test distance score just below the 1000km boundary."""
    # Score = max(0, 100 - 999.9 / 10) = max(0, 100 - 99.99) = max(0, 0.01) -> rounds to 0
    # Note: int(round(0.01)) == 0
    assert scoring.calculate_distance_score("BOS", "JFK") == 0
    mock_calc_dist.assert_called_once_with(MOCK_AIRPORTS["BOS"], MOCK_AIRPORTS["JFK"])


@patch(
    "backend.services.scoring.get_airport_coords",
    side_effect=lambda code: MOCK_AIRPORTS.get(code.upper()),
)
@patch("backend.services.scoring.calculate_distance_km", return_value=0.0)
def test_calculate_distance_score_zero_distance(
    mock_calc_dist: MagicMock, mock_get_coords: MagicMock
) -> None:
    """Test distance score when distance is zero (should be 100)."""
    # This case is handled by the explicit check `if correct_coords == guessed_coords`
    # But if distance somehow calculated as 0 for different coords:
    # Score = max(0, 100 - 0 / 10) = 100
    assert scoring.calculate_distance_score("BOS", "JFK") == 100  # Using JFK, but mocked dist=0
    mock_calc_dist.assert_called_once_with(MOCK_AIRPORTS["BOS"], MOCK_AIRPORTS["JFK"])

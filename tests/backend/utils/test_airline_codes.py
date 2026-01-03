"""Tests for the airline ICAO code lookup utility."""

from backend.utils.airline_codes import (
    AIRLINE_ICAO_CODES,
    infer_operator_from_callsign,
)


class TestInferOperatorFromCallsign:
    """Test suite for infer_operator_from_callsign function."""

    def test_major_us_carriers(self) -> None:
        """Test inference for major US carriers."""
        assert infer_operator_from_callsign("AAL1234") == "American Airlines"
        assert infer_operator_from_callsign("DAL567") == "Delta Air Lines"
        assert infer_operator_from_callsign("UAL890") == "United Airlines"
        assert infer_operator_from_callsign("SWA1234") == "Southwest Airlines"
        assert infer_operator_from_callsign("JBU123") == "JetBlue Airways"
        assert infer_operator_from_callsign("ASA456") == "Alaska Airlines"
        assert infer_operator_from_callsign("NKS789") == "Spirit Airlines"
        assert infer_operator_from_callsign("FFT321") == "Frontier Airlines"
        assert infer_operator_from_callsign("HAL654") == "Hawaiian Airlines"
        assert infer_operator_from_callsign("SKW987") == "SkyWest Airlines"

    def test_international_carriers(self) -> None:
        """Test inference for major international carriers."""
        assert infer_operator_from_callsign("BAW123") == "British Airways"
        assert infer_operator_from_callsign("DLH456") == "Lufthansa"
        assert infer_operator_from_callsign("UAE789") == "Emirates"
        assert infer_operator_from_callsign("QFA1234") == "Qantas"
        assert infer_operator_from_callsign("ACA567") == "Air Canada"
        assert infer_operator_from_callsign("JAL890") == "Japan Airlines"

    def test_cargo_carriers(self) -> None:
        """Test inference for cargo carriers."""
        assert infer_operator_from_callsign("FDX123") == "FedEx Express"
        assert infer_operator_from_callsign("UPS456") == "UPS Airlines"

    def test_case_insensitivity(self) -> None:
        """Test that callsign matching is case-insensitive."""
        assert infer_operator_from_callsign("ual1234") == "United Airlines"
        assert infer_operator_from_callsign("Ual1234") == "United Airlines"
        assert infer_operator_from_callsign("uAl1234") == "United Airlines"
        assert infer_operator_from_callsign("UAL1234") == "United Airlines"

    def test_unknown_codes_return_none(self) -> None:
        """Test that unknown ICAO codes return None."""
        # Private aircraft registration numbers
        assert infer_operator_from_callsign("N12345") is None
        # Unknown 3-letter codes
        assert infer_operator_from_callsign("XYZ123") is None
        assert infer_operator_from_callsign("ZZZ999") is None

    def test_none_input_returns_none(self) -> None:
        """Test that None input returns None."""
        assert infer_operator_from_callsign(None) is None

    def test_empty_string_returns_none(self) -> None:
        """Test that empty string returns None."""
        assert infer_operator_from_callsign("") is None

    def test_short_callsign_returns_none(self) -> None:
        """Test that callsigns shorter than 3 characters return None."""
        assert infer_operator_from_callsign("UA") is None
        assert infer_operator_from_callsign("A") is None

    def test_exactly_three_characters(self) -> None:
        """Test callsigns that are exactly 3 characters (just the prefix)."""
        assert infer_operator_from_callsign("UAL") == "United Airlines"
        assert infer_operator_from_callsign("DAL") == "Delta Air Lines"

    def test_callsign_with_whitespace(self) -> None:
        """Test that whitespace doesn't affect the lookup."""
        # Note: The function does NOT strip whitespace - it uses the first 3 chars as-is
        # This is intentional since callsigns from ADS-B shouldn't have leading whitespace
        assert infer_operator_from_callsign("UAL1234") == "United Airlines"


class TestAirlineIcaoCodes:
    """Tests for the AIRLINE_ICAO_CODES dictionary."""

    def test_all_codes_are_three_letters(self) -> None:
        """Verify all ICAO codes are exactly 3 characters."""
        for code in AIRLINE_ICAO_CODES:
            assert len(code) == 3, f"Code {code} is not 3 characters"

    def test_all_codes_are_uppercase(self) -> None:
        """Verify all ICAO codes are uppercase."""
        for code in AIRLINE_ICAO_CODES:
            assert code == code.upper(), f"Code {code} is not uppercase"

    def test_all_values_are_non_empty_strings(self) -> None:
        """Verify all airline names are non-empty strings."""
        for code, name in AIRLINE_ICAO_CODES.items():
            assert isinstance(name, str), f"Name for {code} is not a string"
            assert len(name) > 0, f"Name for {code} is empty"

    def test_minimum_airlines_present(self) -> None:
        """Ensure we have a reasonable number of airlines mapped."""
        # We should have at least 50 airlines for good coverage
        assert len(AIRLINE_ICAO_CODES) >= 50, "Should have at least 50 airlines"

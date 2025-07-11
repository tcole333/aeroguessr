"""Test the populate_airports_data script."""

import json

# Import the script module
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from backend.scripts.populate_airports_data import main

# Sample CSV data for testing
SAMPLE_CSV_DATA = (
    "id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,continent,"
    "iso_country,iso_region,municipality,scheduled_service,icao_code,iata_code,"
    "gps_code,local_code,home_link,wikipedia_link,keywords\n"
    "1,KATL,large_airport,Hartsfield Jackson Atlanta International Airport,"
    "33.6367,-84.428101,1026,NA,US,US-GA,Atlanta,yes,KATL,ATL,KATL,ATL,,,\n"
    "2,KBOS,large_airport,Logan International Airport,42.36197,-71.0079,19,"
    "NA,US,US-MA,Boston,yes,KBOS,BOS,KBOS,BOS,,,\n"
    "3,KJFK,large_airport,John F Kennedy International Airport,40.63974,"
    "-73.77853,13,NA,US,US-NY,New York,yes,KJFK,JFK,KJFK,JFK,,,\n"
    "4,SMALL,small_airport,Small Regional Airport,41.123,-72.456,100,"
    "NA,US,US-CT,Hartford,yes,KSMALL,SML,KSMALL,SML,,,\n"
    "5,MEDIUM,medium_airport,Medium City Airport,42.789,-73.123,200,"
    "NA,US,US-VT,Burlington,yes,KMED,MED,KMED,MED,,,\n"
    "6,NOIA,medium_airport,No IATA Airport,43.456,-74.789,300,"
    "NA,US,US-NH,Manchester,yes,KNOIA,,KNOIA,NOIA,,,\n"
    "7,NOSCHED,large_airport,No Schedule Airport,44.123,-75.456,400,"
    "NA,US,US-ME,Portland,no,KNOSCH,NSC,KNOSCH,NSC,,,\n"
    "8,HELI,heliport,City Heliport,40.123,-73.456,50,"
    "NA,US,US-NY,New York,yes,KHELI,HLP,KHELI,HLP,,,\n"
    "9,CLOSED,closed,Closed Airport,39.123,-72.456,100,"
    "NA,US,US-NJ,Newark,no,KCLOSED,CLS,KCLOSED,CLS,,,\n"
    "10,NOLOC,large_airport,No Location Airport,,,500,"
    "NA,US,US-CA,Los Angeles,yes,KNOLOC,NLC,KNOLOC,NLC,,,"
)


class TestPopulateAirportsData:
    """Test the populate_airports_data script."""

    @patch("urllib.request.urlopen")
    def test_script_execution(self, mock_urlopen):
        """Test that the script executes and creates both output files."""
        # Mock the response
        mock_response = MagicMock()
        mock_response.read.return_value = SAMPLE_CSV_DATA.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create directory structure
            backend_dir = temp_path / "sample_data"
            backend_dir.mkdir(parents=True)
            frontend_dir = temp_path / "frontend" / "src" / "assets"
            frontend_dir.mkdir(parents=True)

            # Patch Path resolution to use temp directory
            with patch("pathlib.Path.resolve") as mock_resolve:
                mock_resolve.return_value = (
                    temp_path / "backend" / "scripts" / "populate_airports_data.py"
                )

                # Run the script
                main()

                # Check backend file
                backend_file = backend_dir / "airports_min.json"
                assert backend_file.exists()
                backend_data = json.loads(backend_file.read_text())

                # Should include all airports with coordinates (9 out of 10 in sample)
                assert len(backend_data) == 9

                # Check frontend file
                frontend_file = frontend_dir / "airports.json"
                assert frontend_file.exists()
                frontend_data = json.loads(frontend_file.read_text())

                # Should only include large/medium airports with IATA codes and scheduled service
                # ATL, BOS, JFK (large, scheduled), MED (medium, scheduled),
                # NSC (large, no scheduled)
                # Note: Large airports are included even without scheduled service
                assert len(frontend_data) == 5

                # Verify data structure
                for airport in frontend_data:
                    assert "iata" in airport
                    assert "icao" in airport
                    assert "name" in airport
                    assert "municipality" in airport
                    assert "country" in airport
                    assert "lat" in airport
                    assert "lon" in airport
                    assert airport["iata"] is not None  # Frontend requires IATA

                # Check specific airports are included
                iata_codes = [a["iata"] for a in frontend_data]
                assert "ATL" in iata_codes
                assert "BOS" in iata_codes
                assert "JFK" in iata_codes
                assert "MED" in iata_codes

                # Check excluded airports
                assert "SML" not in iata_codes  # small airport
                # large airport included despite no scheduled service
                assert "NSC" in iata_codes
                assert "HLP" not in iata_codes  # heliport
                assert "CLS" not in iata_codes  # closed
                assert "NLC" not in iata_codes  # no location

    @patch("urllib.request.urlopen")
    def test_backend_data_format(self, mock_urlopen):
        """Test that backend data maintains minimal format."""
        # Mock the response
        mock_response = MagicMock()
        mock_response.read.return_value = SAMPLE_CSV_DATA.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create directory structure
            backend_dir = temp_path / "sample_data"
            backend_dir.mkdir(parents=True)
            frontend_dir = temp_path / "frontend" / "src" / "assets"
            frontend_dir.mkdir(parents=True)

            # Patch Path resolution to use temp directory
            with patch("pathlib.Path.resolve") as mock_resolve:
                mock_resolve.return_value = (
                    temp_path / "backend" / "scripts" / "populate_airports_data.py"
                )

                # Run the script
                main()

                # Check backend file format
                backend_file = backend_dir / "airports_min.json"
                backend_data = json.loads(backend_file.read_text())

                # Backend should have minimal fields only
                for airport in backend_data:
                    assert set(airport.keys()) == {"iata", "icao", "lat", "lon"}
                    assert isinstance(airport["lat"], float)
                    assert isinstance(airport["lon"], float)
                    # ICAO is always present in our data
                    assert airport["icao"] is not None

    @patch("urllib.request.urlopen")
    def test_frontend_filtering_logic(self, mock_urlopen):
        """Test the filtering logic for frontend data."""
        # Create test data with edge cases
        edge_case_csv = (
            "id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,continent,"
            "iso_country,iso_region,municipality,scheduled_service,icao_code,"
            "iata_code,gps_code,local_code,home_link,wikipedia_link,keywords\n"
            "1,KLARGE1,large_airport,Large with Schedule,40.0,-70.0,100,"
            "NA,US,US-NY,New York,yes,KLARGE1,LG1,,,,,\n"
            "2,KLARGE2,large_airport,Large no Schedule,41.0,-71.0,100,"
            "NA,US,US-NY,New York,no,KLARGE2,LG2,,,,,\n"
            "3,KMED1,medium_airport,Medium with Schedule,42.0,-72.0,100,"
            "NA,US,US-NY,New York,yes,KMED1,MD1,,,,,\n"
            "4,KMED2,medium_airport,Medium no Schedule,43.0,-73.0,100,"
            "NA,US,US-NY,New York,no,KMED2,MD2,,,,,\n"
            "5,KSMALL,small_airport,Small with Schedule,44.0,-74.0,100,"
            "NA,US,US-NY,New York,yes,KSMALL,SM1,,,,,"
        )

        mock_response = MagicMock()
        mock_response.read.return_value = edge_case_csv.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create directory structure
            backend_dir = temp_path / "sample_data"
            backend_dir.mkdir(parents=True)
            frontend_dir = temp_path / "frontend" / "src" / "assets"
            frontend_dir.mkdir(parents=True)

            # Patch Path resolution to use temp directory
            with patch("pathlib.Path.resolve") as mock_resolve:
                mock_resolve.return_value = (
                    temp_path / "backend" / "scripts" / "populate_airports_data.py"
                )

                # Run the script
                main()

                # Check frontend filtering
                frontend_file = frontend_dir / "airports.json"
                frontend_data = json.loads(frontend_file.read_text())

                # Should include:
                # - LG1: large with scheduled service
                # - LG2: large without scheduled service (large airports always included)
                # - MD1: medium with scheduled service
                # Should NOT include:
                # - MD2: medium without scheduled service
                # - SM1: small airport regardless of scheduled service

                iata_codes = [a["iata"] for a in frontend_data]
                assert len(frontend_data) == 3
                assert "LG1" in iata_codes
                assert "LG2" in iata_codes
                assert "MD1" in iata_codes
                assert "MD2" not in iata_codes
                assert "SM1" not in iata_codes

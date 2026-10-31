"""Airline ICAO code lookup utilities.

This module provides a mapping from ICAO airline codes (3-letter prefixes in
callsigns) to human-readable airline names. This is used to infer operator
information when the scheduled flight lookup doesn't return it.
"""

from typing import Optional

# ICAO airline codes to short airline names, adapted from "List of airline codes" by Wikipedia
# contributors (https://en.wikipedia.org/wiki/List_of_airline_codes), CC BY-SA 4.0. This table
# is under CC BY-SA 4.0 too, not the MIT License (NOTICE.md).
AIRLINE_ICAO_CODES: dict[str, str] = {
    # Major US carriers
    "AAL": "American Airlines",
    "DAL": "Delta Air Lines",
    "UAL": "United Airlines",
    "SWA": "Southwest Airlines",
    "JBU": "JetBlue Airways",
    "ASA": "Alaska Airlines",
    "NKS": "Spirit Airlines",
    "FFT": "Frontier Airlines",
    "HAL": "Hawaiian Airlines",
    "SKW": "SkyWest Airlines",
    "AAY": "Allegiant Air",
    "ENY": "Envoy Air",
    "RPA": "Republic Airways",
    "PDT": "Piedmont Airlines",
    "MES": "Mesa Airlines",
    "JIA": "PSA Airlines",
    "CPZ": "Compass Airlines",
    "GJS": "GoJet Airlines",
    "ASH": "Mesa Airlines",
    "EJA": "NetJets",
    # Major international carriers
    "BAW": "British Airways",
    "AFR": "Air France",
    "DLH": "Lufthansa",
    "KLM": "KLM",
    "UAE": "Emirates",
    "QFA": "Qantas",
    "ACA": "Air Canada",
    "JAL": "Japan Airlines",
    "ANA": "All Nippon Airways",
    "CPA": "Cathay Pacific",
    "SIA": "Singapore Airlines",
    "QTR": "Qatar Airways",
    "ETD": "Etihad Airways",
    "THY": "Turkish Airlines",
    "SAS": "Scandinavian Airlines",
    "AUA": "Austrian Airlines",
    "TAP": "TAP Air Portugal",
    "IBE": "Iberia",
    "VLG": "Vueling",
    "EZY": "easyJet",
    "RYR": "Ryanair",
    "WZZ": "Wizz Air",
    "ICE": "Icelandair",
    "FIN": "Finnair",
    "LOT": "LOT Polish Airlines",
    "CSA": "Czech Airlines",
    "SWR": "Swiss International Air Lines",
    "BEL": "Brussels Airlines",
    "KAL": "Korean Air",
    "AAR": "Asiana Airlines",
    "CCA": "Air China",
    "CES": "China Eastern Airlines",
    "CSN": "China Southern Airlines",
    "HDA": "Hong Kong Airlines",
    "EVA": "EVA Air",
    "CAL": "China Airlines",
    "THA": "Thai Airways",
    "MAS": "Malaysia Airlines",
    "SLK": "Silkair",
    "VNA": "Vietnam Airlines",
    "PAL": "Philippine Airlines",
    "GIA": "Garuda Indonesia",
    "ANZ": "Air New Zealand",
    "AEE": "Aegean Airlines",
    "TAM": "LATAM Airlines Brasil",
    "LAN": "LATAM Airlines Chile",
    "AVA": "Avianca",
    "AMX": "Aeromexico",
    "AZU": "Azul Brazilian Airlines",
    "GOL": "Gol Transportes Aereos",
    "CMP": "Copa Airlines",
    "ARE": "Aires Colombia",
    "SAA": "South African Airways",
    "ETH": "Ethiopian Airlines",
    "KQA": "Kenya Airways",
    "RWD": "RwandAir",
    "RAM": "Royal Air Maroc",
    "MSR": "EgyptAir",
    "GFA": "Gulf Air",
    "SVA": "Saudia",
    "MEA": "Middle East Airlines",
    "RJA": "Royal Jordanian",
    "ELY": "El Al",
    "FDB": "flydubai",
    "AXB": "Air India Express",
    "AIC": "Air India",
    "IGO": "IndiGo",
    "SEJ": "SpiceJet",
    "VTI": "Vistara",
    "CEB": "Cebu Pacific",
    "APJ": "Peach Aviation",
    "JST": "Jetstar Airways",
    "VOZ": "Virgin Australia",
    "WJA": "WestJet",
    "POE": "Porter Airlines",
    "SLI": "Sun Country Airlines",
    "BZA": "SATA Air Acores",
    # Cargo carriers
    "FDX": "FedEx Express",
    "UPS": "UPS Airlines",
    "ABW": "AirBridgeCargo",
    "GTI": "Atlas Air",
    "CLX": "Cargolux",
    "MPH": "Martinair Cargo",
    "SQC": "Singapore Airlines Cargo",
    "CKK": "China Cargo Airlines",
}


def infer_operator_from_callsign(callsign: str | None) -> Optional[str]:
    """Infer airline name from ICAO callsign prefix.

    Most commercial flights use a callsign format of AAA1234 where AAA is the
    3-letter ICAO airline code. This function extracts that prefix and looks
    it up in a known airline codes mapping.

    Args:
        callsign: The aircraft callsign (e.g., "UAL1234", "DAL567").

    Returns:
        The airline name if found, None otherwise.

    Examples:
        >>> infer_operator_from_callsign("UAL1234")
        'United Airlines'
        >>> infer_operator_from_callsign("DAL567")
        'Delta Air Lines'
        >>> infer_operator_from_callsign("N12345")  # Private aircraft
        None
        >>> infer_operator_from_callsign(None)
        None
    """
    if not callsign or len(callsign) < 3:
        return None

    # Extract the 3-letter prefix and normalize to uppercase
    prefix = callsign[:3].upper()

    return AIRLINE_ICAO_CODES.get(prefix)

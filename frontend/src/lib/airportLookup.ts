import airports from '@data/airports.json';

interface Airport {
  iata: string;
  icao: string;
  name: string;
  municipality: string;
  country: string;
  lat: number;
  lon: number;
}

// Build lookup maps (once on load)
const byIcao = new Map<string, Airport>();
const byIata = new Map<string, Airport>();

(airports as Airport[]).forEach((a) => {
  if (a.icao) byIcao.set(a.icao.toUpperCase(), a);
  if (a.iata) byIata.set(a.iata.toUpperCase(), a);
});

/**
 * Look up an airport by ICAO or IATA code
 */
export function getAirportByCode(code: string): Airport | null {
  if (!code) return null;
  const upper = code.toUpperCase();
  return byIcao.get(upper) || byIata.get(upper) || null;
}

/**
 * Return the error to show for a typed guess code, or null if it can be scored.
 *
 * The server scores against the same dataset and rejects unknown codes with
 * the same message (UNKNOWN_AIRPORT_CODE), so checking here keeps the player
 * from submitting a guess that would be refused.
 */
export function guessCodeError(code: string): string | null {
  if (getAirportByCode(code)) return null;
  return `Unknown airport code '${code}'. Enter an IATA (ORD) or ICAO (KORD) code.`;
}

// Cities with multiple major airports - use IATA code instead of city name
// to avoid confusion (e.g., "JFK" vs "LGA" vs "EWR" all in NYC area)
const MULTI_AIRPORT_CITIES = new Set([
  'NEW YORK',
  'LOS ANGELES',
  'CHICAGO',
  'WASHINGTON',
  'LONDON',
  'PARIS',
  'TOKYO',
  'SAN FRANCISCO',
  'DALLAS',
  'HOUSTON',
  'MIAMI', // MIA, FLL, PBI all serve Miami metro
  'NEWARK', // Part of NYC metro
  'OAKLAND', // Part of SF Bay Area
  'BURBANK', // Part of LA metro
  'ONTARIO', // Part of LA metro
  'ATLANTA', // ATL is dominant but Peachtree-Dekalb exists
]);

/**
 * Format an airport code for user-friendly display
 *
 * Rules:
 * - For multi-airport cities: use IATA code (e.g., "JFK", "LAX")
 * - For single-airport cities: use city name (e.g., "Boston", "Denver")
 * - For unknown codes: return original code as fallback
 */
export function formatAirportDisplay(code: string | null | undefined): string {
  if (!code) return '???';

  const airport = getAirportByCode(code);
  if (!airport) return code; // Fallback to code if not in database

  const city = airport.municipality?.toUpperCase();

  // Multi-airport cities: use IATA code for disambiguation
  if (city && MULTI_AIRPORT_CITIES.has(city)) {
    return airport.iata || code;
  }

  // Single-airport cities: use city name for friendliness
  return airport.municipality || airport.iata || code;
}

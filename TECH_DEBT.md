## ⛳ Item: Flight Route Enrichment via AeroAPI

- **Context:** The ingest service (`backend/ingest/enrichment.py`) uses FlightAware's AeroAPI (`/flights/{hex_ident}`) to fetch origin and destination airport ICAO codes for flights, supplementing data from OpenSky.
- **Potential issues:** Relies on a free tier AeroAPI key (`FLIGHTAWARE_API_KEY`) which may have usage limits. The lookup by hex ID might occasionally return multiple flights or fail for specific aircraft (e.g., military, very recent flights not yet fully processed by FlightAware). Error handling and caching (6hr TTL) are in place, but heavy usage could exceed free tier limits.
- **Why accepted:** Provides the necessary origin/destination data for the core game mechanic, which was unavailable via the free OpenSky endpoint. Free tier is sufficient for development and personal use.
- **Next step:** Monitor API usage. If limits are hit, investigate paid tiers or alternative data fusion strategies. Refine logic for handling ambiguous responses from `/flights/{hex_ident}` if necessary.
- **Code Ref:** `backend/ingest/enrichment.py#L124` (Location of `fetch_aeroapi_route` function)

---

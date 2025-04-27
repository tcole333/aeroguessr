## ⛳ Item: Flight Route Enrichment via AeroAPI

- **Context:** The ingest service (`backend/ingest/enrichment.py`) uses FlightAware's AeroAPI (`/flights/{hex_ident}`) to fetch origin and destination airport ICAO codes for flights, supplementing data from OpenSky.
- **Potential issues:** Relies on a free tier AeroAPI key (`FLIGHTAWARE_API_KEY`) which may have usage limits. The lookup by hex ID might occasionally return multiple flights or fail for specific aircraft (e.g., military, very recent flights not yet fully processed by FlightAware). Error handling and caching (6hr TTL) are in place, but heavy usage could exceed free tier limits.
- **Why accepted:** Provides the necessary origin/destination data for the core game mechanic, which was unavailable via the free OpenSky endpoint. Free tier is sufficient for development and personal use.
- **Next step:** Monitor API usage. If limits are hit, investigate paid tiers or alternative data fusion strategies. Refine logic for handling ambiguous responses from `/flights/{hex_ident}` if necessary.
- **Code Ref:** `backend/ingest/enrichment.py#L124` (Location of `fetch_aeroapi_route` function)

---

## ⛳ Item: Placeholder Distance Calculation in Scoring

- **Context:** The `calculate_distance_km` function in `backend/services/scoring.py` uses a very rough approximation based on latitude/longitude differences.
- **Potential issues:** Scoring in Distance mode will be inaccurate and potentially unfair.
- **Why accepted:** Allows testing the Distance scoring mode logic flow without implementing full geographic calculations and airport data loading immediately.
- **Next step:** Replace the placeholder with a proper geodesic distance calculation using a library like `geopy`. This also requires implementing the `get_airport_coords` function to fetch real coordinates, likely from a cached airport dataset.
- **Code Ref:** `backend/services/scoring.py#L47`

---

## ⛳ Item: Plane Selection Logic Placeholder

- **Context:** The `selectPlane` handler in `backend/routes/rooms.py` currently uses placeholder values (`BOS`, `destination`) for the correct airport code and guess direction. It also doesn't validate the selected plane hex against currently tracked aircraft.
- **Potential issues:** The game cannot function correctly as the correct answer isn't determined from live/sample data. Invalid plane selections are possible.
- **Why accepted:** Allows implementing the round state machine and message flow without integrating the plane data lookup logic from the ingest service immediately.
- **Next step:** Modify the `selectPlane` handler to:
  1. Fetch the selected plane's data (e.g., from `plane:{hex}` in Redis).
  2. Validate that the plane exists and has origin/destination data.
  3. Determine the correct `correct_airport_code` (origin or destination based on flight phase/direction).
  4. Determine the `guess_direction` to send to clients.
- **Code Ref:** `backend/routes/rooms.py#L498`

---

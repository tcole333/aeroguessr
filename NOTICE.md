# Third-party notices

AeroGuessr's own code is under the MIT License ([LICENSE](LICENSE)). It also uses the data, services, fonts and icons below, each under its own terms.

## Data in this repository

- **Airports:** [OurAirports](https://ourairports.com/data/), released into the public domain. `data/airports.json` is generated from it by `backend/scripts/populate_airports_data.py`.
- **Airline names:** Wikipedia contributors, [List of airline codes](https://en.wikipedia.org/wiki/List_of_airline_codes), under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
  - The `AIRLINE_ICAO_CODES` table in `backend/utils/airline_codes.py` is adapted from it.
  - That table is therefore also under CC BY-SA 4.0, not MIT.

## Services used at runtime

AeroGuessr calls these services; it doesn't ship their data.

- **The map:** tiles and styles from [OpenFreeMap](https://openfreemap.org), with the [OpenMapTiles](https://openmaptiles.org) schema.
  - The map data is © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), under the ODbL 1.0.
  - The map shows the attribution "OpenFreeMap © OpenMapTiles Data from OpenStreetMap", and it must stay visible.
- **FlightAware AeroAPI:** the optional source of flight routes.
  - Each operator of an AeroGuessr instance uses their own key and is bound by FlightAware's [terms of use](https://www.flightaware.com/about/terms-of-use).
  - This project includes no AeroAPI key or data.
- **Google Fonts:** the browser loads IBM Plex Sans and Share Tech Mono from `fonts.googleapis.com`. Both are under the SIL Open Font License 1.1.

## Fonts and icons in the frontend

- **DM Sans** (`frontend/src/assets/fonts/DMSans-*.woff2`): copyright 2014 The DM Sans Project Authors, SIL Open Font License 1.1. The license text is in `frontend/src/assets/fonts/DMSans-OFL.txt`.
- **DSEG14 Classic** (`frontend/src/assets/fonts/DSEG14Classic-*.woff2`): copyright keshikan, with Reserved Font Name "DSEG", SIL Open Font License 1.1. The license text is in `frontend/src/assets/fonts/DSEG-LICENSE.txt`. Source: [github.com/keshikan/DSEG](https://github.com/keshikan/DSEG).
- **Plane icon** (`frontend/src/assets/icons/plane-generic.svg`, plus the favicons in `frontend/public/` rendered from it): the "flight" icon from Google's [Material Icons](https://github.com/google/material-design-icons), under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).

## Software dependencies

The Python and JavaScript libraries are listed in `pyproject.toml` and `frontend/package.json`, each under its own license. The published images include them.
- Almost all are under permissive licenses (MIT, ISC, BSD, Apache 2.0); `certifi` is under MPL 2.0.
- **`react-leaflet` and `@react-leaflet/core` are under the [Hippocratic License 2.1](https://firstdonoharm.dev/version/2/1/license/).** It is an ethical-use license, not an OSI-approved open-source license. The frontend bundle, and so the published frontend image, includes them.

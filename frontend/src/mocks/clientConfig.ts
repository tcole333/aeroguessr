import type { ClientConfig } from '../services/apiService';

/** A Seattle install, so a test notices anything still pinned to Boston. */
export const seattleClientConfig: ClientConfig = {
  center: { lat: 47.4502, lon: -122.3088 },
  monitored_airport: {
    icao: 'KSEA',
    iata: 'SEA',
    name: 'Seattle–Tacoma International Airport',
    position: { lat: 47.447943, lon: -122.310276 },
  },
  max_antenna_range_km: 250,
  map_style_url: 'https://tiles.openfreemap.org/styles/liberty',
  attributions: [
    '<a href="https://openfreemap.org" target="_blank" rel="noopener noreferrer">OpenFreeMap</a>',
    'Routes from Example Data',
  ],
  version: '1.2.3-alpha.4+0abc123',
};

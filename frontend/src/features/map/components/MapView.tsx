import { MapContainer, TileLayer } from 'react-leaflet';

const centerLat = parseFloat(
  (import.meta.env.VITE_CENTER_LAT ?? import.meta.env.CENTER_LAT) ?? '42.3656',
);
const centerLon = parseFloat(
  (import.meta.env.VITE_CENTER_LON ?? import.meta.env.CENTER_LON) ?? '-71.0096',
);
const tileUrl =
  import.meta.env.VITE_OSM_TILE_URL ??
  import.meta.env.OSM_TILE_URL ??
  'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';

export default function MapView(): JSX.Element {
  return (
    <MapContainer
      center={[centerLat, centerLon]}
      zoom={12}
      className="h-full w-full"
    >
      <TileLayer url={tileUrl} attribution="&copy; OpenStreetMap contributors" />
    </MapContainer>
  );
}

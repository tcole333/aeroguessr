import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import { useStore } from '../../../hooks/useStore';
import { selectPlaneMap } from '../../planes/selectors';
import { selectSelectedPlane } from '../../game/selectors';
import PlaneMarker from './PlaneMarker';
import type { Map as LeafletMap } from 'leaflet';

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

// Component to handle map focusing
function MapController() {
  const map = useMap();
  const planes = useStore(selectPlaneMap);
  const selectedPlaneHex = useStore(selectSelectedPlane);

  useEffect(() => {
    if (selectedPlaneHex) {
      const selectedPlane = planes[selectedPlaneHex];
      if (selectedPlane?.lat && selectedPlane?.lon) {
        map.setView([selectedPlane.lat, selectedPlane.lon], 14, {
          animate: true,
          duration: 1.0
        });
      }
    }
  }, [selectedPlaneHex, planes, map]);

  return null;
}

interface MapViewProps {
  onPlaneClick?: (hex: string) => void;
}

export default function MapView({ onPlaneClick }: MapViewProps): JSX.Element {
  const planes = useStore(selectPlaneMap);
  const selectedPlaneHex = useStore(selectSelectedPlane);

  // Debug logging removed for production - uncomment if needed for debugging
  // useEffect(() => {
  //   const planeCount = Object.keys(planes).length;
  //   console.log('[MapView] Planes in store:', planeCount);
  //   if (planeCount > 0 && planeCount <= 5) {
  //     console.log('[MapView] Plane details:', planes);
  //   }
  // }, [planes]);

  return (
    <MapContainer
      center={[centerLat, centerLon]}
      zoom={12}
      className="h-full w-full"
    >
      <TileLayer url={tileUrl} attribution="&copy; OpenStreetMap contributors" />
      <MapController />
      {Object.values(planes).map((plane) => (
        <PlaneMarker
          key={plane.hex_ident}
          plane={plane}
          isSelected={plane.hex_ident === selectedPlaneHex}
          onClick={onPlaneClick}
        />
      ))}
    </MapContainer>
  );
}

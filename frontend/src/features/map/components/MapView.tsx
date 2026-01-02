import { useEffect, useRef, useState } from 'react';
import { MapContainer, TileLayer, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import { useStore } from '../../../hooks/useStore';
import { selectPlaneMap } from '../../planes/selectors';
import { selectRound, selectSelectedPlane, selectUsedPlanes } from '../../game/selectors';
import { selectExpandedPlane, selectRetroMode } from '../../ui/selectors';
import PlaneMarker from './PlaneMarker';
import RetroMapAnnotations from './RetroMapAnnotations';
import RetroMapOverlay from './RetroMapOverlay';

const centerLat = parseFloat(
  (import.meta.env.VITE_CENTER_LAT ?? import.meta.env.CENTER_LAT) ?? '42.3656',
);
const centerLon = parseFloat(
  (import.meta.env.VITE_CENTER_LON ?? import.meta.env.CENTER_LON) ?? '-71.0096',
);
const standardTileUrl =
  import.meta.env.VITE_OSM_TILE_URL ??
  import.meta.env.OSM_TILE_URL ??
  'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';

// Retro tile options - light chart base with no labels
const retroTileUrl = 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}{r}.png';
const standardAttribution = '&copy; OpenStreetMap contributors';
const retroAttribution = '&copy; OpenStreetMap contributors, &copy; CARTO';
const defaultZoom = 12;

// Component to handle map focusing and zoom tracking
function MapController({
  onZoomChange,
  focusPlaneHex,
  selectedPlaneHex,
}: {
  onZoomChange?: (zoom: number) => void;
  focusPlaneHex?: string | null;
  selectedPlaneHex?: string | null;
}) {
  const map = useMap();
  const planes = useStore(selectPlaneMap);
  const lastFocusRef = useRef<string | null>(null);
  const lastSelectedRef = useRef<string | null>(null);

  // Track zoom changes
  useMapEvents({
    zoomend: () => {
      onZoomChange?.(map.getZoom());
    },
  });

  // Set initial zoom
  useEffect(() => {
    onZoomChange?.(map.getZoom());
  }, [map, onZoomChange]);

  useEffect(() => {
    if (!focusPlaneHex) {
      lastFocusRef.current = null;
      return;
    }
    if (focusPlaneHex === lastFocusRef.current) return;
    const focusedPlane = planes[focusPlaneHex];
    if (focusedPlane?.lat && focusedPlane?.lon) {
      const targetZoom = Math.max(map.getZoom(), defaultZoom);
      map.setView([focusedPlane.lat, focusedPlane.lon], targetZoom, {
        animate: true,
        duration: 0.8,
      });
      lastFocusRef.current = focusPlaneHex;
    }
  }, [focusPlaneHex, planes, map]);

  useEffect(() => {
    if (!selectedPlaneHex || focusPlaneHex) {
      lastSelectedRef.current = null;
      return;
    }
    if (selectedPlaneHex === lastSelectedRef.current) return;
    const selectedPlane = planes[selectedPlaneHex];
    if (selectedPlane?.lat && selectedPlane?.lon) {
      map.panTo([selectedPlane.lat, selectedPlane.lon], {
        animate: true,
        duration: 0.6,
      });
      lastSelectedRef.current = selectedPlaneHex;
    }
  }, [selectedPlaneHex, focusPlaneHex, planes, map]);

  return null;
}

interface MapViewProps {
  onPlaneClick?: (hex: string) => void;
}

function ResetViewControl(): null {
  const map = useMap();

  useEffect(() => {
    // Create a custom control using Leaflet's Control class
    const ResetControl = L.Control.extend({
      onAdd: () => {
        const container = L.DomUtil.create('div', 'leaflet-control leaflet-bar retro-map-reset');
        const button = L.DomUtil.create('button', 'retro-map-reset-button', container);
        button.type = 'button';
        button.innerText = 'Reset';
        button.setAttribute('aria-label', 'Reset map view');
        button.setAttribute('title', 'Reset map view');

        L.DomEvent.on(button, 'click', (event) => {
          L.DomEvent.stopPropagation(event);
          map.setView([centerLat, centerLon], defaultZoom, {
            animate: true,
            duration: 0.8,
          });
        });

        L.DomEvent.disableClickPropagation(container);
        return container;
      },
    });

    const control = new ResetControl({ position: 'topright' });
    control.addTo(map);

    return () => {
      control.remove();
    };
  }, [map]);

  return null;
}

export default function MapView({ onPlaneClick }: MapViewProps): JSX.Element {
  const planes = useStore(selectPlaneMap);
  const selectedPlaneHex = useStore(selectSelectedPlane);
  const round = useStore(selectRound);
  const usedPlanes = useStore(selectUsedPlanes);
  const retroMode = useStore(selectRetroMode);
  const expandedPlaneHex = useStore(selectExpandedPlane);
  const [currentZoom, setCurrentZoom] = useState(defaultZoom);

  const tileUrl = retroMode ? retroTileUrl : standardTileUrl;
  const attribution = retroMode ? retroAttribution : standardAttribution;

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
      zoom={defaultZoom}
      className="h-full w-full"
    >
      <TileLayer
        key={retroMode ? 'retro' : 'standard'}
        url={tileUrl}
        attribution={attribution}
        className={retroMode ? 'retro-map-base-layer' : undefined}
      />
      {retroMode && <RetroMapOverlay />}
      {retroMode && <RetroMapAnnotations />}
      <MapController
        onZoomChange={setCurrentZoom}
        focusPlaneHex={expandedPlaneHex}
        selectedPlaneHex={selectedPlaneHex}
      />
      <ResetViewControl />
      {Object.values(planes).map((plane) => {
        const isActive = round?.state === 'guessing' && round?.hex === plane.hex_ident;
        const isUsed = usedPlanes.has(plane.hex_ident);
        return (
          <PlaneMarker
            key={plane.hex_ident}
            plane={plane}
            isSelected={plane.hex_ident === selectedPlaneHex}
            isActive={isActive}
            isUsed={isUsed}
            onClick={onPlaneClick}
            zoom={currentZoom}
          />
        );
      })}
    </MapContainer>
  );
}

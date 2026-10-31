import { useEffect, useRef, useState } from 'react';
import { MapContainer, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import { useStore } from '../../../hooks/useStore';
import { selectPlaneMap } from '../../planes/selectors';
import { selectRound, selectSelectedPlane, selectUsedPlanes } from '../../game/selectors';
import { selectExpandedPlane, selectRetroMode } from '../../ui/selectors';
import { selectClientConfig, selectClientConfigStatus, selectLoadClientConfig } from '../../config/selectors';
import { useLoadClientConfig } from '../../config/useLoadClientConfig';
import type { ClientConfig } from '../../../services/apiService';
import MapPlaceholder from './MapPlaceholder';
import PlaneMarker from './PlaneMarker';
import RetroMapAnnotations from './RetroMapAnnotations';
import RetroMapOverlay from './RetroMapOverlay';
import VectorBaseLayer from './VectorBaseLayer';

const defaultZoom = 12;
// Leaflet takes its zoom limit from tile layers, which this map no longer has.
const maxZoom = 18;

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

function ResetViewControl({ center }: { center: ClientConfig['center'] }): null {
  const map = useMap();
  const { lat, lon } = center;

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
          map.setView([lat, lon], defaultZoom, {
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
  }, [map, lat, lon]);

  return null;
}

/**
 * The game map. It opens on the receiver's location from the client config, so it shows a
 * placeholder until that config has loaded.
 */
export default function MapView({ onPlaneClick }: MapViewProps): JSX.Element {
  useLoadClientConfig();
  const status = useStore(selectClientConfigStatus);
  const clientConfig = useStore(selectClientConfig);
  const loadClientConfig = useStore(selectLoadClientConfig);

  if (clientConfig === null) {
    return <MapPlaceholder failed={status === 'failed'} onRetry={() => void loadClientConfig()} />;
  }
  return <ConfiguredMap clientConfig={clientConfig} onPlaneClick={onPlaneClick} />;
}

interface ConfiguredMapProps extends MapViewProps {
  clientConfig: ClientConfig;
}

function ConfiguredMap({ clientConfig, onPlaneClick }: ConfiguredMapProps): JSX.Element {
  const planes = useStore(selectPlaneMap);
  const selectedPlaneHex = useStore(selectSelectedPlane);
  const round = useStore(selectRound);
  const usedPlanes = useStore(selectUsedPlanes);
  const retroMode = useStore(selectRetroMode);
  const expandedPlaneHex = useStore(selectExpandedPlane);
  const [currentZoom, setCurrentZoom] = useState(defaultZoom);

  const { center } = clientConfig;

  return (
    <MapContainer
      center={[center.lat, center.lon]}
      zoom={defaultZoom}
      maxZoom={maxZoom}
      className="h-full w-full"
    >
      <VectorBaseLayer
        styleUrl={clientConfig.map_style_url}
        attribution={clientConfig.attributions.join(' | ')}
        placeLabelsOnly={retroMode}
      />
      {retroMode && <RetroMapOverlay />}
      {retroMode && <RetroMapAnnotations airport={clientConfig.monitored_airport} />}
      <MapController
        onZoomChange={setCurrentZoom}
        focusPlaneHex={expandedPlaneHex}
        selectedPlaneHex={selectedPlaneHex}
      />
      <ResetViewControl center={center} />
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

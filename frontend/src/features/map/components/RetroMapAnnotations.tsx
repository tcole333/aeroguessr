import { useMemo } from 'react';
import L from 'leaflet';
import { CircleMarker, Marker, Pane } from 'react-leaflet';
import type { MonitoredAirport } from '../../../services/apiService';

interface RetroMapAnnotationsProps {
  airport: MonitoredAirport;
}

// Built from DOM nodes rather than an HTML string, so a name from the airport dataset
// is always shown as text.
function createAirportLabelIcon(code: string, name: string | null): L.DivIcon {
  const label = document.createElement('div');
  const codeLine = document.createElement('div');
  codeLine.className = 'retro-map-label retro-map-label--primary';
  codeLine.textContent = code;
  label.append(codeLine);
  if (name) {
    const nameLine = document.createElement('div');
    nameLine.className = 'retro-map-label retro-map-label--secondary';
    nameLine.textContent = name;
    label.append(nameLine);
  }
  return L.divIcon({ className: '', html: label, iconSize: [1, 1], iconAnchor: [0, 0] });
}

/**
 * Chart Mode's label for the monitored airport. Towns are named by the basemap's own place
 * labels. Nothing is drawn when the airport's position is unknown.
 */
export default function RetroMapAnnotations({
  airport,
}: RetroMapAnnotationsProps): JSX.Element | null {
  const code = airport.iata ?? airport.icao;
  const icon = useMemo(() => createAirportLabelIcon(code, airport.name), [code, airport.name]);

  if (!airport.position) return null;
  const position: L.LatLngTuple = [airport.position.lat, airport.position.lon];

  return (
    <>
      <Pane name="retro-labels" style={{ zIndex: 420 }} />
      <CircleMarker
        center={position}
        radius={2.6}
        pane="retro-labels"
        pathOptions={{ className: 'retro-map-label-dot' }}
      />
      <Marker position={position} pane="retro-labels" icon={icon} interactive={false} />
    </>
  );
}

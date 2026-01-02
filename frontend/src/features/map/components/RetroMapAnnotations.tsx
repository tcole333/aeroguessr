import L from 'leaflet';
import { CircleMarker, Marker, Pane } from 'react-leaflet';

type CityLabel = {
  id: string;
  name: string;
  lat: number;
  lon: number;
  tier: 'primary' | 'secondary';
};

const cityLabels: CityLabel[] = [
  { id: 'boston', name: 'BOSTON', lat: 42.3601, lon: -71.0589, tier: 'primary' },
  { id: 'salem', name: 'SALEM', lat: 42.5195, lon: -70.8967, tier: 'secondary' },
  { id: 'cambridge', name: 'CAMBRIDGE', lat: 42.3736, lon: -71.1097, tier: 'secondary' },
  { id: 'worcester', name: 'WORCESTER', lat: 42.2626, lon: -71.8023, tier: 'secondary' },
  { id: 'providence', name: 'PROVIDENCE', lat: 41.824, lon: -71.4128, tier: 'secondary' },
  { id: 'portsmouth', name: 'PORTSMOUTH', lat: 43.0718, lon: -70.7626, tier: 'secondary' },
];

const createLabelIcon = (name: string, tier: CityLabel['tier']) =>
  L.divIcon({
    className: '',
    html: `<div class="retro-map-label retro-map-label--${tier}">${name}</div>`,
    iconSize: [1, 1],
    iconAnchor: [0, 0],
  });

export default function RetroMapAnnotations(): JSX.Element {
  return (
    <>
      <Pane name="retro-labels" style={{ zIndex: 420 }} />

      {cityLabels.map((label) => (
        <CircleMarker
          key={`${label.id}-dot`}
          center={[label.lat, label.lon]}
          radius={label.tier === 'primary' ? 2.6 : 2}
          pane="retro-labels"
          pathOptions={{ className: 'retro-map-label-dot' }}
        />
      ))}

      {cityLabels.map((label) => (
        <Marker
          key={label.id}
          position={[label.lat, label.lon]}
          pane="retro-labels"
          icon={createLabelIcon(label.name, label.tier)}
          interactive={false}
        />
      ))}
    </>
  );
}

import React from 'react';
import { Marker, Polyline } from 'react-leaflet';
import L from 'leaflet';
import type { PlaneState } from '../../common/types';
import planeIconUrl from '@/assets/icons/plane-generic.svg';

export interface PlaneMarkerProps {
  plane: PlaneState;
}

const iconSize: [number, number] = [24, 24];
const iconAnchor: [number, number] = [12, 12];

function createIcon(rotation: number): L.DivIcon {
  return L.divIcon({
    html: `<img src="${planeIconUrl}" class="plane-icon" style="width:24px;height:24px;transform: rotate(${rotation}deg);"/>`,
    iconSize,
    iconAnchor,
    className: ''
  });
}

const PlaneMarkerComponent: React.FC<PlaneMarkerProps> = ({ plane }) => {
  const { lat, lon, hdg, trail } = plane;

  const icon = React.useMemo(() => createIcon(hdg ?? 0), [hdg]);

  const trailSegments = React.useMemo(() => {
    if (!trail || trail.length < 2) return null;
    const segments = [] as JSX.Element[];
    for (let i = trail.length - 1; i > 0; i -= 1) {
      const start = [trail[i][0], trail[i][1]] as [number, number];
      const end = [trail[i - 1][0], trail[i - 1][1]] as [number, number];
      const opacity = (trail.length - i) / trail.length;
      segments.push(
        <Polyline
          key={i}
          positions={[start, end]}
          pathOptions={{ color: '#3b82f6', opacity, weight: 2 }}
        />,
      );
    }
    return segments;
  }, [trail]);

  if (lat == null || lon == null) return null;

  return (
    <>
      <Marker position={[lat, lon]} icon={icon} />
      {trailSegments}
    </>
  );
};

const PlaneMarker = React.memo(PlaneMarkerComponent);

export default PlaneMarker;

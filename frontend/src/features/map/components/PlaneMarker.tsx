import React from 'react';
import { Marker, Polyline } from 'react-leaflet';
import L from 'leaflet';
import type { PlaneState } from '../../common/types';
import planeIconUrl from '@/assets/icons/plane-generic.svg';

export interface PlaneMarkerProps {
  plane: PlaneState;
  isSelected?: boolean;
  onClick?: (hex: string) => void;
}

const iconSize: [number, number] = [24, 24];
const iconAnchor: [number, number] = [12, 12];

function createIcon(rotation: number, isSelected: boolean = false): L.DivIcon {
  const selectedStyle = isSelected
    ? 'border: 2px solid #3b82f6; border-radius: 50%; background: rgba(59, 130, 246, 0.2); padding: 2px;'
    : '';

  return L.divIcon({
    html: `<div style="${selectedStyle}"><img src="${planeIconUrl}" class="plane-icon" style="width:24px;height:24px;transform: rotate(${rotation}deg);"/></div>`,
    iconSize: isSelected ? [32, 32] : iconSize,
    iconAnchor: isSelected ? [16, 16] : iconAnchor,
    className: ''
  });
}

const PlaneMarkerComponent: React.FC<PlaneMarkerProps> = ({ plane, isSelected, onClick }) => {
  const { lat, lon, trail, lat_v, lon_v } = plane;

  // Calculate heading from velocity vectors
  const hdg = React.useMemo(() => {
    if (lat_v === 0 && lon_v === 0) return 0;
    // Convert velocity to bearing in degrees
    const bearing = Math.atan2(lon_v, lat_v) * (180 / Math.PI);
    return (bearing + 360) % 360; // Normalize to 0-360
  }, [lat_v, lon_v]);

  const icon = React.useMemo(() => createIcon(hdg, isSelected), [hdg, isSelected]);

  const handleClick = React.useCallback(() => {
    if (onClick) {
      onClick(plane.hex_ident);
    }
  }, [onClick, plane.hex_ident]);

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
      <Marker
        position={[lat, lon]}
        icon={icon}
        eventHandlers={{
          click: handleClick,
        }}
      />
      {trailSegments}
    </>
  );
};

const PlaneMarker = React.memo(PlaneMarkerComponent);

export default PlaneMarker;

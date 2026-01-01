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

  // Adjust rotation: the SVG points up (north), which is 0 degrees
  // No adjustment needed as our heading calculation already matches this
  return L.divIcon({
    html: `<div style="${selectedStyle}"><img src="${planeIconUrl}" class="plane-icon" style="width:24px;height:24px;transform: rotate(${rotation}deg);"/></div>`,
    iconSize: isSelected ? [32, 32] : iconSize,
    iconAnchor: isSelected ? [16, 16] : iconAnchor,
    className: ''
  });
}

const PlaneMarkerComponent: React.FC<PlaneMarkerProps> = ({ plane, isSelected, onClick }) => {
  const { lat, lon, trail, lat_v, lon_v, track } = plane;

  // Keep track of previous heading for stability using useRef to avoid stale closures
  const previousHeadingRef = React.useRef(0);

  // Use raw ADS-B track if available, otherwise calculate from velocity
  const hdg = React.useMemo(() => {
    // Prefer raw ADS-B track when available (most accurate)
    if (track != null && !isNaN(track)) {
      previousHeadingRef.current = track;
      return track;
    }

    // Fallback: Calculate heading from velocity vectors
    // Calculate speed magnitude
    const speed = Math.sqrt(lat_v * lat_v + lon_v * lon_v);

    // If speed is very low, try to calculate from trail
    const MIN_SPEED_THRESHOLD = 0.001; // About 0.06 knots
    if (speed < MIN_SPEED_THRESHOLD) {
      // Try to calculate heading from trail if available
      if (trail && trail.length >= 2) {
        const lastPoint = trail[trail.length - 1];
        const secondLastPoint = trail[trail.length - 2];
        const trailLatDiff = lastPoint[0] - secondLastPoint[0];
        const trailLonDiff = lastPoint[1] - secondLastPoint[1];
        const trailSpeed = Math.sqrt(trailLatDiff * trailLatDiff + trailLonDiff * trailLonDiff);

        if (trailSpeed > MIN_SPEED_THRESHOLD) {
          // Same calculation as velocity-based heading
          const trailBearing = Math.atan2(trailLonDiff, trailLatDiff) * (180 / Math.PI);
          const trailHeading = (trailBearing + 360) % 360;
          previousHeadingRef.current = trailHeading;
          return trailHeading;
        }
      }
      // If no trail or trail speed too low, maintain previous heading
      return previousHeadingRef.current;
    }

    // Convert velocity to bearing in degrees
    // atan2 expects (y, x) where x is east-west (longitude) and y is north-south (latitude)
    // We want: 0° = North, 90° = East, 180° = South, 270° = West
    const bearing = Math.atan2(lon_v, lat_v) * (180 / Math.PI);
    const newHeading = (bearing + 360) % 360; // Normalize to 0-360

    // Apply smoothing for small heading changes
    const headingDiff = Math.abs(newHeading - previousHeadingRef.current);
    const MIN_HEADING_CHANGE = 5; // Degrees

    // Only update heading if change is significant
    if (headingDiff < MIN_HEADING_CHANGE || headingDiff > (360 - MIN_HEADING_CHANGE)) {
      return previousHeadingRef.current;
    }

    previousHeadingRef.current = newHeading;
    return newHeading;
  }, [track, lat_v, lon_v, trail]);

  const icon = React.useMemo(() => createIcon(hdg, isSelected), [hdg, isSelected]);

  const handleClick = React.useCallback(() => {
    if (onClick) {
      onClick(plane.hex_ident);
    }
  }, [onClick, plane.hex_ident]);

  const trailSegments = React.useMemo(() => {
    if (!trail || trail.length < 2) return null;

    // Limit to last 10 updates for shorter trails
    const maxPoints = 10;
    const recentTrail = trail.slice(-maxPoints);

    if (recentTrail.length < 2) return null;

    const segments = [] as JSX.Element[];
    for (let i = 0; i < recentTrail.length - 1; i++) {
      const start = [recentTrail[i][0], recentTrail[i][1]] as [number, number];
      const end = [recentTrail[i + 1][0], recentTrail[i + 1][1]] as [number, number];
      // Opacity decreases for older segments (i=0 is oldest)
      const opacity = (i + 1) / recentTrail.length;
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

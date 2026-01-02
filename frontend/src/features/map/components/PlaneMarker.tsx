import React from 'react';
import { Marker, Polyline } from 'react-leaflet';
import L from 'leaflet';
import type { PlaneState } from '../../common/types';
import planeIconUrl from '@/assets/icons/plane-generic.svg';
import { useStore } from '../../../hooks/useStore';
import { selectRetroMode } from '../../ui/selectors';

export interface PlaneMarkerProps {
  plane: PlaneState;
  isSelected?: boolean;
  isActive?: boolean;
  isUsed?: boolean;
  onClick?: (hex: string) => void;
  zoom?: number;
}

// Calculate icon size based on zoom level
// Base size at zoom 12, scales up as you zoom in
function getIconSizeForZoom(zoom: number, isSelected: boolean): { size: number; anchor: number } {
  // Scale factor: 1.0 at zoom 10, increases as zoom goes higher
  // Each zoom level increases size by ~15%
  const baseZoom = 10;
  const baseSize = 20;
  const scaleFactor = Math.pow(1.15, zoom - baseZoom);
  const size = Math.round(baseSize * scaleFactor);
  const selectedSize = Math.round(size * 1.3);
  const finalSize = isSelected ? selectedSize : size;
  return {
    size: Math.max(16, Math.min(finalSize, 64)), // Clamp between 16 and 64
    anchor: Math.round(finalSize / 2),
  };
}

function createIcon(
  rotation: number,
  isSelected: boolean = false,
  isActive: boolean = false,
  isUsed: boolean = false,
  retroMode: boolean = false,
  zoom: number = 12,
): L.DivIcon {
  const { size, anchor } = getIconSizeForZoom(zoom, isSelected);
  const finalRotation = rotation;

  // Retro mode: amber planes with radar-style glow
  if (retroMode) {
    const state = isActive ? 'active' : isSelected ? 'selected' : isUsed ? 'used' : 'idle';
    const ring = isActive
      ? `<circle cx="12" cy="12" r="10.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-opacity="0.9" stroke-dasharray="2 3"/>`
      : '';

    return L.divIcon({
      html: `<div class="retro-plane-marker-inner">
        <svg viewBox="0 0 24 24" width="${size}" height="${size}" style="transform: rotate(${finalRotation}deg);">
          ${ring}
          <path fill="currentColor" d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
        </svg>
      </div>`,
      iconSize: [size, size],
      iconAnchor: [anchor, anchor],
      className: `retro-plane-marker retro-plane-marker--${state}`,
    });
  }

  const selectedStyle = isSelected
    ? 'border: 2px solid #3b82f6; border-radius: 50%; background: rgba(59, 130, 246, 0.2); padding: 2px;'
    : '';

  // Adjust rotation: the SVG points up (north), which is 0 degrees
  // No adjustment needed as our heading calculation already matches this
  return L.divIcon({
    html: `<div style="${selectedStyle}"><img src="${planeIconUrl}" class="plane-icon" style="width:${size}px;height:${size}px;transform: rotate(${finalRotation}deg);"/></div>`,
    iconSize: [size, size],
    iconAnchor: [anchor, anchor],
    className: ''
  });
}

const PlaneMarkerComponent: React.FC<PlaneMarkerProps> = ({
  plane,
  isSelected = false,
  isActive = false,
  isUsed = false,
  onClick,
  zoom = 12,
}) => {
  const { lat, lon, trail, lat_v, lon_v, track } = plane;
  const retroMode = useStore(selectRetroMode);

  // Keep track of previous heading for stability using useRef to avoid stale closures
  const previousHeadingRef = React.useRef(0);

  // Use raw ADS-B track if available, otherwise calculate from trail or velocity
  const hdg = React.useMemo(() => {
    // Prefer raw ADS-B track when available (most accurate)
    if (track != null && !isNaN(track)) {
      previousHeadingRef.current = track;
      return track;
    }

    // Fallback 1: Calculate heading from trail
    const getTrailHeading = () => {
      if (!trail || trail.length < 2) return null;
      const lastPoint = trail[trail.length - 1];
      const secondLastPoint = trail[trail.length - 2];
      const trailLatDiff = lastPoint[0] - secondLastPoint[0];
      const trailLonDiff = lastPoint[1] - secondLastPoint[1];
      const trailSpeed = Math.sqrt(trailLatDiff * trailLatDiff + trailLonDiff * trailLonDiff);
      const MIN_TRAIL_SPEED = 0.00001;
      if (trailSpeed < MIN_TRAIL_SPEED) return null;
      const trailBearing = Math.atan2(trailLonDiff, trailLatDiff) * (180 / Math.PI);
      return (trailBearing + 360) % 360;
    };

    const trailHeading = getTrailHeading();
    if (trailHeading != null) {
      const headingDiff = Math.abs(trailHeading - previousHeadingRef.current);
      const MIN_HEADING_CHANGE = 5;
      if (headingDiff < MIN_HEADING_CHANGE || headingDiff > (360 - MIN_HEADING_CHANGE)) {
        return previousHeadingRef.current;
      }
      previousHeadingRef.current = trailHeading;
      return trailHeading;
    }

    // Fallback 2: Calculate heading from velocity vectors
    // Calculate speed magnitude
    const speed = Math.sqrt(lat_v * lat_v + lon_v * lon_v);

    // If speed is very low, try to calculate from trail
    const MIN_SPEED_THRESHOLD = 0.001; // About 0.06 knots
    if (speed < MIN_SPEED_THRESHOLD) {
      // Try to calculate heading from trail if available
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

  const icon = React.useMemo(
    () => createIcon(hdg, isSelected, isActive, isUsed, retroMode, zoom),
    [hdg, isSelected, isActive, isUsed, retroMode, zoom],
  );

  const handleClick = React.useCallback(() => {
    if (onClick) {
      onClick(plane.hex_ident);
    }
  }, [onClick, plane.hex_ident]);

  const trailSegments = React.useMemo(() => {
    if (!trail || trail.length < 2) return null;

    // Limit to last updates for manageable trail length
    const maxPoints = zoom <= 9 ? 180 : zoom <= 11 ? 120 : zoom <= 13 ? 90 : 70;
    const recentTrail = trail.slice(-maxPoints);

    if (recentTrail.length < 2) return null;

    const retroTrailColor = isActive ? '#D4844A' : isSelected ? '#BB6830' : isUsed ? '#8B5A2B' : '#9A5020';
    const baseOpacity = isUsed ? 0.45 : isActive ? 0.95 : isSelected ? 0.9 : 0.82;
    const zoomFactor = Math.min(2.2, Math.max(0.85, 1 + (12 - zoom) * 0.16));
    const baseWeight = (isActive ? 3.4 : isSelected ? 3.1 : 2.8) * zoomFactor;
    const haloWeight = baseWeight + 2;
    const haloColor = '#4A5A48';
    const dashArray = isUsed ? '2 6' : undefined;
    const trailColor = retroMode ? retroTrailColor : '#3b82f6';
    const segments = [] as JSX.Element[];
    for (let i = 0; i < recentTrail.length - 1; i++) {
      const start = [recentTrail[i][0], recentTrail[i][1]] as [number, number];
      const end = [recentTrail[i + 1][0], recentTrail[i + 1][1]] as [number, number];
      // Opacity decreases for older segments (i=0 is oldest)
      const t = (i + 1) / recentTrail.length;
      const fade = 0.35 + 0.65 * t;
      const opacity = (retroMode ? baseOpacity : 0.9) * fade;
      if (retroMode) {
        segments.push(
          <Polyline
            key={`halo-${i}`}
            positions={[start, end]}
            pathOptions={{
              color: haloColor,
              opacity: opacity * 0.35,
              weight: haloWeight,
              lineCap: 'round',
              lineJoin: 'round',
            }}
          />,
        );
      }
      segments.push(
        <Polyline
          key={`trail-${i}`}
          positions={[start, end]}
          pathOptions={{
            color: trailColor,
            opacity,
            weight: retroMode ? baseWeight : 2,
            dashArray: retroMode ? dashArray : undefined,
            lineCap: 'round',
            lineJoin: 'round',
          }}
        />,
      );
    }
    return segments;
  }, [trail, retroMode, isActive, isSelected, isUsed, zoom]);

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

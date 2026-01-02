import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';

/**
 * Injects a color overlay div INSIDE Leaflet's tile pane structure.
 * This is necessary because pseudo-elements on .leaflet-container can't
 * blend with tile content due to Leaflet's transformed stacking contexts.
 *
 * By placing the overlay inside the tile-pane, we're in the same stacking
 * context and mix-blend-mode works properly.
 */
export default function RetroMapOverlay(): null {
  const map = useMap();
  const overlayRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = map.getContainer();
    const tilePane = container.querySelector('.leaflet-tile-pane');

    if (!tilePane || overlayRef.current) return;

    // Create the color overlay element using theme-tuned CSS
    const overlay = document.createElement('div');
    overlay.className = 'retro-map-color-overlay';
    overlay.style.cssText = `
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      z-index: 1;
    `;

    tilePane.appendChild(overlay);
    overlayRef.current = overlay;

    return () => {
      if (overlayRef.current) {
        overlayRef.current.remove();
        overlayRef.current = null;
      }
    };
  }, [map]);

  return null;
}

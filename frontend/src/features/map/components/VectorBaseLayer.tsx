import { useEffect } from 'react';
import { useMap } from 'react-leaflet';
import type L from 'leaflet';

// The context attributes MapLibre requests in Map._setupPainter.
const MAPLIBRE_CONTEXT_ATTRIBUTES: WebGLContextAttributes = {
  alpha: true,
  depth: true,
  stencil: true,
  premultipliedAlpha: true,
};

function canRenderWebGL2(): boolean {
  if (typeof WebGL2RenderingContext === 'undefined') return false;
  try {
    const context = document
      .createElement('canvas')
      .getContext('webgl2', MAPLIBRE_CONTEXT_ATTRIBUTES);
    if (!context) return false;
    context.getExtension('WEBGL_lose_context')?.loseContext();
    return true;
  } catch {
    return false;
  }
}

export interface VectorBaseLayerProps {
  styleUrl: string;
  attribution: string;
  /** Show only the basemap's place names, as Chart Mode does. */
  placeLabelsOnly?: boolean;
}

/**
 * Renders a MapLibre vector basemap under the Leaflet layers. Without WebGL2 the
 * map keeps working with no basemap, and the MapLibre bundle is never downloaded.
 */
export default function VectorBaseLayer({
  styleUrl,
  attribution,
  placeLabelsOnly = false,
}: VectorBaseLayerProps): null {
  const map = useMap();

  useEffect(() => {
    if (!canRenderWebGL2()) {
      console.warn('[VectorBaseLayer] WebGL2 unavailable; rendering map without a basemap');
      return undefined;
    }

    let isCancelled = false;
    let layer: L.Layer | null = null;

    import('../maplibreLayer')
      .then(({ addVectorLayer }) => {
        if (isCancelled) return;
        layer = addVectorLayer(map, { styleUrl, attribution, placeLabelsOnly });
      })
      .catch((error: unknown) => {
        console.warn('[VectorBaseLayer] Failed to load vector basemap', String(error));
      });

    return () => {
      isCancelled = true;
      layer?.remove();
    };
  }, [map, styleUrl, attribution, placeLabelsOnly]);

  return null;
}

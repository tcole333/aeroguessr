// The only module that imports MapLibre. VectorBaseLayer loads it lazily so the
// ~280 kB gzip GL bundle stays out of the home page.
import type L from 'leaflet';
import { maplibreGL } from '@maplibre/maplibre-gl-leaflet';
import {
  setWorkerUrl,
  type ErrorEventType,
  type Evented,
  type Map as MaplibreMap,
  type StyleSpecification,
} from 'maplibre-gl';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import 'maplibre-gl/dist/maplibre-gl.css';

setWorkerUrl(maplibreWorkerUrl);

export interface VectorLayerOptions {
  styleUrl: string;
  attribution: string;
  /** Hide every basemap label except place names (cities, towns, villages). */
  placeLabelsOnly: boolean;
}

// OpenMapTiles styles, which include every OpenFreeMap style, keep place names in this layer.
const PLACE_SOURCE_LAYER = 'place';

export function nonPlaceLabelLayerIds(style: StyleSpecification): string[] {
  return style.layers
    .filter((layer) => layer.type === 'symbol' && layer['source-layer'] !== PLACE_SOURCE_LAYER)
    .map((layer) => layer.id);
}

function hideNonPlaceLabels(glMap: MaplibreMap): void {
  for (const layerId of nonPlaceLabelLayerIds(glMap.getStyle())) {
    glMap.setLayoutProperty(layerId, 'visibility', 'none');
  }
}

// Without an 'error' listener MapLibre console.errors every failed tile.
export function warnOnFirstError(glMap: Pick<Evented<ErrorEventType>, 'on'>): void {
  let hasWarned = false;
  glMap.on('error', (event) => {
    if (hasWarned) return;
    hasWarned = true;
    console.warn('[VectorBaseLayer] Basemap error', String(event.error));
  });
}

// Leaflet registers the layer and binds its map events before onAdd runs, so a
// MapLibre constructor failure leaves handlers that dereference a missing GL map.
function detachFailedLayer(map: L.Map, layer: L.MaplibreGL): void {
  layer.onRemove = () => {
    layer.getContainer().remove();
    return layer;
  };
  map.removeLayer(layer);
}

export function addVectorLayer(map: L.Map, options: VectorLayerOptions): L.Layer {
  const layer = maplibreGL({
    style: options.styleUrl,
    attributionControl: { customAttribution: options.attribution },
  });

  try {
    layer.addTo(map);
  } catch (error) {
    detachFailedLayer(map, layer);
    throw error;
  }

  const glMap = layer.getMaplibreMap();
  warnOnFirstError(glMap);
  if (options.placeLabelsOnly) {
    glMap.once('style.load', () => hideNonPlaceLabels(glMap));
  }
  return layer;
}

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import L from 'leaflet';
import { ErrorEvent, Evented, type ErrorEventType, type StyleSpecification } from 'maplibre-gl';
import { addVectorLayer, nonPlaceLabelLayerIds, warnOnFirstError } from '../maplibreLayer';

const layerOptions = {
  styleUrl: 'https://tiles.openfreemap.org/styles/positron',
  attribution: 'OpenFreeMap',
  placeLabelsOnly: false,
};

// Real Leaflet, the real plugin and real MapLibre: only the GPU is simulated.
describe('addVectorLayer when MapLibre cannot start', () => {
  let mapElement: HTMLDivElement;
  let map: L.Map;

  beforeEach(() => {
    // The GPU refuses a WebGL2 context, as on a device that passed VectorBaseLayer's
    // preflight but fails MapLibre's own request. MapLibre then throws GPUInitializationError.
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    mapElement = document.createElement('div');
    document.body.append(mapElement);
    map = L.map(mapElement).setView([42.3656, -71.0096], 12);
  });

  afterEach(() => {
    mapElement.remove();
    vi.restoreAllMocks();
  });

  it('reports the MapLibre start-up error to the caller', () => {
    expect(() => addVectorLayer(map, layerOptions)).toThrow(/WebGL2/);
  });

  it('leaves the map movable', () => {
    expect(() => addVectorLayer(map, layerOptions)).toThrow();
    expect(() => map.setView([42.4, -71.1], 13, { animate: false })).not.toThrow();
  });

  it('leaves the map removable', () => {
    expect(() => addVectorLayer(map, layerOptions)).toThrow();
    expect(() => map.remove()).not.toThrow();
  });

  it('removes the basemap container', () => {
    expect(() => addVectorLayer(map, layerOptions)).toThrow();
    expect(mapElement.querySelector('.leaflet-gl-layer')).toBeNull();
  });
});

describe('nonPlaceLabelLayerIds', () => {
  it('lists the label layers that do not name places', () => {
    const style: StyleSpecification = {
      version: 8,
      sources: { openmaptiles: { type: 'vector', url: 'https://tiles.openfreemap.org/planet' } },
      layers: [
        { id: 'background', type: 'background' },
        { id: 'water', type: 'fill', source: 'openmaptiles', 'source-layer': 'water' },
        { id: 'label_city', type: 'symbol', source: 'openmaptiles', 'source-layer': 'place' },
        {
          id: 'highway-name-major',
          type: 'symbol',
          source: 'openmaptiles',
          'source-layer': 'transportation_name',
        },
      ],
    };
    expect(nonPlaceLabelLayerIds(style)).toEqual(['highway-name-major']);
  });
});

class ErrorSource extends Evented<ErrorEventType> {}

describe('warnOnFirstError', () => {
  it('warns once per basemap however many tiles fail', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const glMap = new ErrorSource();
    warnOnFirstError(glMap);
    glMap.fire(new ErrorEvent(new Error('tile 1 failed')));
    glMap.fire(new ErrorEvent(new Error('tile 2 failed')));
    expect(warn.mock.calls).toEqual([['[VectorBaseLayer] Basemap error', 'Error: tile 1 failed']]);
    warn.mockRestore();
  });
});

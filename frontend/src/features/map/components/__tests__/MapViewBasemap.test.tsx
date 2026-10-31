import { act, render } from '@testing-library/react';
import type L from 'leaflet';
import MapView from '../MapView';
import { StoreContext } from '../../../../store/createRootStore';
import { addVectorLayer, type VectorLayerOptions } from '../../maplibreLayer';
import { seattleClientConfig } from '../../../../mocks/clientConfig';
import { createStoreWithClientConfig } from '../../../../mocks/configuredStore';

// jsdom cannot run MapLibre, so the lazily loaded GL module is replaced by a fake
// that records which basemaps are on the map. Everything else is real.
vi.mock('../../maplibreLayer', () => ({ addVectorLayer: vi.fn() }));

const addVectorLayerMock = vi.mocked(addVectorLayer);

interface FakeBasemap {
  options: VectorLayerOptions;
  isRemoved: boolean;
}

describe('MapView basemap', () => {
  let basemaps: FakeBasemap[];

  function emulateWebGL2(): void {
    vi.stubGlobal('WebGL2RenderingContext', class {});
    const webgl2Context = { getExtension: () => null } as unknown as WebGL2RenderingContext;
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(((contextId: string) =>
      contextId === 'webgl2' ? webgl2Context : null) as typeof HTMLCanvasElement.prototype.getContext);
  }

  function liveBasemaps(): VectorLayerOptions[] {
    return basemaps.filter((basemap) => !basemap.isRemoved).map((basemap) => basemap.options);
  }

  async function renderMap({ chartMode = true } = {}) {
    const store = await createStoreWithClientConfig();
    if (!chartMode) store.getState().ui.toggleRetroMode();
    const utils = render(
      <StoreContext.Provider value={store}>
        <MapView />
      </StoreContext.Provider>,
    );
    return { store, ...utils };
  }

  // Lets every pending lazy import('../maplibreLayer') settle.
  async function flushBasemapLoad(): Promise<void> {
    await act(() => vi.dynamicImportSettled());
  }

  beforeEach(() => {
    basemaps = [];
    addVectorLayerMock.mockReset();
    addVectorLayerMock.mockImplementation((_map, options) => {
      const basemap: FakeBasemap = { options, isRemoved: false };
      basemaps.push(basemap);
      const layer = {
        remove: () => {
          basemap.isRemoved = true;
          return layer;
        },
      };
      return layer as unknown as L.Layer;
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  describe('with WebGL2', () => {
    beforeEach(emulateWebGL2);

    it('renders the configured basemap with only its place labels in Chart Mode', async () => {
      await renderMap();
      await flushBasemapLoad();
      expect(liveBasemaps()).toEqual([
        {
          styleUrl: seattleClientConfig.map_style_url,
          attribution: expect.any(String),
          placeLabelsOnly: true,
        },
      ]);
    });

    it('credits every data source the client config lists', async () => {
      await renderMap();
      await flushBasemapLoad();
      expect(liveBasemaps()[0].attribution).toBe(
        `${seattleClientConfig.attributions[0]} | ${seattleClientConfig.attributions[1]}`,
      );
    });

    it('shows all basemap labels outside Chart Mode', async () => {
      await renderMap({ chartMode: false });
      await flushBasemapLoad();
      expect(liveBasemaps().map((options) => options.placeLabelsOnly)).toEqual([false]);
    });

    it('swaps to a fully labelled basemap when Chart Mode is turned off', async () => {
      const { store } = await renderMap();
      await flushBasemapLoad();
      act(() => store.getState().ui.toggleRetroMode());
      await flushBasemapLoad();
      expect(liveBasemaps().map((options) => options.placeLabelsOnly)).toEqual([false]);
    });

    it('removes the basemap when the map unmounts', async () => {
      const { unmount } = await renderMap();
      await flushBasemapLoad();
      unmount();
      expect(basemaps.map((basemap) => basemap.isRemoved)).toEqual([true]);
    });

    it('does not add a basemap when the map unmounts before MapLibre loads', async () => {
      const { unmount } = await renderMap();
      unmount();
      await flushBasemapLoad();
      expect(basemaps).toEqual([]);
    });

    it('warns with the error message when the basemap fails to start', async () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
      addVectorLayerMock.mockImplementation(() => {
        throw new Error('WebGL2 context refused');
      });
      await renderMap();
      await flushBasemapLoad();
      expect(warn).toHaveBeenCalledWith(
        '[VectorBaseLayer] Failed to load vector basemap',
        'Error: WebGL2 context refused',
      );
    });
  });

  it('does not load MapLibre without WebGL2', async () => {
    await renderMap();
    await flushBasemapLoad();
    expect(addVectorLayerMock).not.toHaveBeenCalled();
  });
});

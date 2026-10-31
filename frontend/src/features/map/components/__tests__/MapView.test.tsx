import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import L from 'leaflet';
import { http, HttpResponse } from 'msw';
import MapView from '../MapView';
import { StoreContext, createRootStore, type RootStore } from '../../../../store/createRootStore';
import type { PlaneState } from '../../../common/types';
import { server } from '../../../../mocks/server';
import { seattleClientConfig } from '../../../../mocks/clientConfig';
import { createStoreWithClientConfig } from '../../../../mocks/configuredStore';

const seattle = L.latLng(seattleClientConfig.center.lat, seattleClientConfig.center.lon);

function renderMap(store: RootStore) {
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <StoreContext.Provider value={store}>{children}</StoreContext.Provider>
  );
  return render(<MapView />, { wrapper: Wrapper });
}

describe('MapView', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  async function renderMapWithPlanes(planes: PlaneState[] = []) {
    const store = await createStoreWithClientConfig();
    // Toggle retroMode off (default is true) to test standard mode UI
    store.getState().ui.toggleRetroMode();
    store.getState().planes.upsertPlanes(planes);
    return renderMap(store);
  }

  it('renders Leaflet map container', async () => {
    const { container } = await renderMapWithPlanes();
    expect(container.querySelector('.leaflet-container')).toBeInTheDocument();
  });

  it('shows plane markers from store', async () => {
    const plane: PlaneState = {
      hex_ident: 'abcd',
      lat: 0,
      lon: 0,
      alt: 0,
      lat_v: 0,
      lon_v: 0,
      alt_v: 0,
      last_update_ts: 1,
      trail: [[0, 0, 0]],
    };
    const { container } = await renderMapWithPlanes([plane]);
    expect(container.querySelector('.plane-icon')).toBeInTheDocument();
  });

  it('warns that it is rendering without a basemap when WebGL2 is unavailable', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    await renderMapWithPlanes();
    expect(warn).toHaveBeenCalledWith(
      '[VectorBaseLayer] WebGL2 unavailable; rendering map without a basemap',
    );
  });

  it('stops zooming in at zoom 18', async () => {
    const { container } = await renderMapWithPlanes();
    const zoomIn = container.querySelector('.leaflet-control-zoom-in') as HTMLElement;
    for (let zoom = 12; zoom < 18; zoom += 1) {
      fireEvent.click(zoomIn);
    }
    expect(zoomIn).toHaveClass('leaflet-disabled');
  });

  it('opens on the receiver location from the client config', async () => {
    const setView = vi.spyOn(L.Map.prototype, 'setView');
    await renderMapWithPlanes();
    expect(L.latLng(setView.mock.calls[0][0])).toEqual(seattle);
  });

  it('resets the view to the receiver location', async () => {
    await renderMapWithPlanes();
    const setView = vi.spyOn(L.Map.prototype, 'setView').mockImplementation(function (this: L.Map) {
      return this;
    });
    fireEvent.click(screen.getByRole('button', { name: 'Reset map view' }));
    expect(L.latLng(setView.mock.calls[0][0])).toEqual(seattle);
  });

  it('says the map is loading until the client config arrives', () => {
    renderMap(createRootStore());
    expect(screen.getByRole('status')).toHaveTextContent('Loading map…');
  });

  it('opens the map once the client config arrives', async () => {
    const { container } = renderMap(createRootStore());
    await waitFor(() => expect(container.querySelector('.leaflet-container')).toBeInTheDocument());
  });

  it('says the map could not load when the client config fails', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    server.use(http.get('/api/v0/config', () => new HttpResponse(null, { status: 502 })));
    renderMap(createRootStore());
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load the map.");
  });

  it('opens the map when trying again after the client config failed', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    server.use(
      http.get('/api/v0/config', () => new HttpResponse(null, { status: 502 }), { once: true }),
    );
    const { container } = renderMap(createRootStore());
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(container.querySelector('.leaflet-container')).toBeInTheDocument());
  });
});

describe('MapView in Chart Mode', () => {
  async function renderChartMap() {
    const store = await createStoreWithClientConfig();
    return renderMap(store);
  }

  function retroLabels(container: HTMLElement): string[] {
    return Array.from(container.querySelectorAll('.retro-map-label')).map(
      (label) => label.textContent ?? '',
    );
  }

  it('labels only the monitored airport, with its code and name', async () => {
    const { container } = await renderChartMap();
    expect(retroLabels(container)).toEqual(['SEA', 'Seattle–Tacoma International Airport']);
  });

  it('labels an airport without an IATA code by its ICAO code', async () => {
    server.use(
      http.get('/api/v0/config', () =>
        HttpResponse.json({
          ...seattleClientConfig,
          monitored_airport: { ...seattleClientConfig.monitored_airport, iata: null },
        }),
      ),
    );
    const { container } = await renderChartMap();
    expect(retroLabels(container)[0]).toBe('KSEA');
  });

  it('shows an airport name as text, never as markup', async () => {
    server.use(
      http.get('/api/v0/config', () =>
        HttpResponse.json({
          ...seattleClientConfig,
          monitored_airport: { ...seattleClientConfig.monitored_airport, name: '<b>Boeing</b>' },
        }),
      ),
    );
    const { container } = await renderChartMap();
    expect(container.querySelector('.retro-map-label b')).toBeNull();
  });

  it('leaves the airport unlabelled when its position is unknown', async () => {
    server.use(
      http.get('/api/v0/config', () =>
        HttpResponse.json({
          ...seattleClientConfig,
          monitored_airport: { icao: 'ZZZZ', iata: null, name: null, position: null },
        }),
      ),
    );
    const { container } = await renderChartMap();
    expect(retroLabels(container)).toEqual([]);
  });
});

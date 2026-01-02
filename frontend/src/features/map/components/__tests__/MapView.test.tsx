import { render } from '@testing-library/react';
import MapView from '../MapView';
import { StoreContext, createRootStore } from '../../../../store/createRootStore';
import type { PlaneState } from '../../../common/types';

describe('MapView', () => {
  function renderMapWithPlanes(planes: PlaneState[] = []) {
    const store = createRootStore();
    // Toggle retroMode off (default is true) to test standard mode UI
    store.getState().ui.toggleRetroMode();
    store.getState().planes.upsertPlanes(planes);
    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <StoreContext.Provider value={store}>{children}</StoreContext.Provider>
    );
    return render(<MapView />, { wrapper: Wrapper });
  }

  it('renders Leaflet map container', () => {
    const { container } = renderMapWithPlanes();
    expect(container.querySelector('.leaflet-container')).toBeInTheDocument();
  });

  it('shows plane markers from store', () => {
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
    const { container } = renderMapWithPlanes([plane]);
    expect(container.querySelector('.plane-icon')).toBeInTheDocument();
  });
});

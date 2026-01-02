import { render } from '@testing-library/react';
import { MapContainer } from 'react-leaflet';
import PlaneMarker from '../PlaneMarker';
import type { PlaneState } from '../../../common/types';
import { StoreContext, createRootStore } from '../../../../store/createRootStore';

function renderWithMap(child: JSX.Element) {
  const store = createRootStore();
  // Toggle retroMode off (default is true) to test standard mode UI
  store.getState().ui.toggleRetroMode();
  return render(
    <StoreContext.Provider value={store}>
      <MapContainer center={[0, 0]} zoom={5}>
        {child}
      </MapContainer>
    </StoreContext.Provider>,
  );
}

const basePlane: PlaneState = {
  hex_ident: 'abcd',
  lat: 0,
  lon: 0,
  alt: 0,
  lat_v: 0,
  lon_v: 0,
  alt_v: 0,
  last_update_ts: 1,
  trail: [[0, 0, 0]],
  track: null,
};

describe('PlaneMarker', () => {
  it('renders plane icon', () => {
    const { container } = renderWithMap(<PlaneMarker plane={basePlane} />);
    expect(container.querySelector('.plane-icon')).toBeInTheDocument();
  });

  it('renders trail segments', () => {
    const plane: PlaneState = {
      ...basePlane,
      trail: [
        [0, 0, 0],
        [0.01, 0.01, 0],
        [0.02, 0.02, 0],
      ],
    };
    const { container } = renderWithMap(<PlaneMarker plane={plane} />);
    expect(
      container.querySelectorAll('path.leaflet-interactive').length,
    ).toBeGreaterThan(0);
  });

  it('handles empty trail gracefully', () => {
    const plane: PlaneState = { ...basePlane, trail: [] };
    const { container } = renderWithMap(<PlaneMarker plane={plane} />);
    expect(container.querySelectorAll('path.leaflet-interactive').length).toBe(0);
  });

  it('uses ADS-B track for heading when available', () => {
    const plane: PlaneState = {
      ...basePlane,
      track: 90, // Heading east
      lat_v: 0.01, // Would give different heading if used
      lon_v: 0,
    };
    const { container } = renderWithMap(<PlaneMarker plane={plane} />);
    const icon = container.querySelector('.plane-icon');
    expect(icon).toBeInTheDocument();
    // The icon should be rotated 90 degrees (east) based on track, not velocity
    expect(icon).toHaveStyle('transform: rotate(90deg)');
  });

  it('falls back to velocity-based heading when track is null', () => {
    const plane: PlaneState = {
      ...basePlane,
      track: null,
      lat_v: 0.01, // Heading north
      lon_v: 0,
    };
    const { container } = renderWithMap(<PlaneMarker plane={plane} />);
    const icon = container.querySelector('.plane-icon');
    expect(icon).toBeInTheDocument();
    // The icon should be rotated based on velocity (heading north = 0 degrees)
    expect(icon).toHaveStyle('transform: rotate(0deg)');
  });
});

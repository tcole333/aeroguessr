import { render } from '@testing-library/react';
import { MapContainer } from 'react-leaflet';
import PlaneMarker from '../PlaneMarker';
import type { PlaneState } from '../../../common/types';

function renderWithMap(child: JSX.Element) {
  return render(
    <MapContainer center={[0, 0]} zoom={5}>
      {child}
    </MapContainer>,
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
});

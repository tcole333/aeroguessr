import { render } from '@testing-library/react';
import MapView from '../MapView';

describe('MapView', () => {
  it('renders Leaflet map container', () => {
    const { container } = render(<MapView />);
    expect(container.querySelector('.leaflet-container')).toBeInTheDocument();
  });
});

import { render, screen } from '@testing-library/react';
import PlaneDetails from '../PlaneDetails';
import { StoreContext, createRootStore } from '../../../../store/createRootStore';
import type { PlaneState } from '../../../common/types';

function setup(
  plane: PlaneState,
  { host = 'Me', connected = true, isSolo = true } = {},
) {
  const store = createRootStore();
  // Toggle retroMode off (default is true) to test standard mode UI
  store.getState().ui.toggleRetroMode();

  // Add the plane to the store
  store.getState().planes.upsertPlanes([plane]);

  store.setState((s) => {
    s.game.hostNickname = host;
    s.game.isSolo = isSolo;
    s.connection.nickname = 'Me';
    s.connection.playerNickname = 'Me';
  });
  if (connected) {
    store.getState().connection.setStatus('connected');
  }
  const onClose = vi.fn();
  const utils = render(
    <StoreContext.Provider value={store}>
      <PlaneDetails hex={plane.hex_ident} onClose={onClose} />
    </StoreContext.Provider>,
  );
  return { store, onClose, ...utils };
}

describe('PlaneDetails', () => {
  it('shows "Start Round with This Flight" button for flights connected to monitored airport', () => {
    // Plane with origin at KBOS (monitored airport)
    const plane: PlaneState = {
      hex_ident: 'connected_plane',
      lat: 42.3656,
      lon: -71.0096,
      alt: 5000,
      lat_v: 0,
      lon_v: 0,
      alt_v: 0,
      last_update_ts: 1,
      trail: [],
      origin: 'KBOS', // Connected to monitored airport
      destination: 'KLAX',
    };

    setup(plane);

    // The "Start Round with This Flight" button should be visible and enabled
    const startButton = screen.getByRole('button', {
      name: /start round with this flight/i,
    });
    expect(startButton).toBeInTheDocument();
    expect(startButton).not.toBeDisabled();
  });

  it('disables selection for overhead flights not connected to monitored airport', () => {
    // Create plane with origin=KLAX, destination=KJFK (neither is KBOS)
    const overheadPlane: PlaneState = {
      hex_ident: 'overhead_plane',
      lat: 42.3656,
      lon: -71.0096,
      alt: 35000,
      lat_v: 0,
      lon_v: 0,
      alt_v: 0,
      last_update_ts: 1,
      trail: [],
      origin: 'KLAX', // Los Angeles - not KBOS
      destination: 'KJFK', // New York JFK - not KBOS
    };

    setup(overheadPlane);

    // The "Start Round with This Flight" button should NOT be present
    // because the plane is an overhead flight not connected to KBOS
    const startButton = screen.queryByRole('button', {
      name: /start round with this flight/i,
    });
    expect(startButton).not.toBeInTheDocument();
  });

  it('shows flight data even for overhead flights', () => {
    // Create plane with origin=KLAX, destination=KJFK (neither is KBOS)
    const overheadPlane: PlaneState = {
      hex_ident: 'overhead_data',
      lat: 42.3656,
      lon: -71.0096,
      alt: 35000,
      lat_v: 0,
      lon_v: 0,
      alt_v: 0,
      last_update_ts: 1,
      trail: [],
      origin: 'KLAX',
      destination: 'KJFK',
    };

    setup(overheadPlane);

    // Should still display the plane's hex identifier
    expect(screen.getByText(/overhead_data/i)).toBeInTheDocument();

    // Should still display altitude
    expect(screen.getByText(/35,000/)).toBeInTheDocument();
  });

  it('shows selection button for flights with destination at monitored airport', () => {
    // Plane arriving at KBOS
    const arrivingPlane: PlaneState = {
      hex_ident: 'arriving_plane',
      lat: 42.3656,
      lon: -71.0096,
      alt: 10000,
      lat_v: 0,
      lon_v: 0,
      alt_v: -50, // Descending
      last_update_ts: 1,
      trail: [],
      origin: 'KJFK',
      destination: 'KBOS', // Connected to monitored airport via destination
    };

    setup(arrivingPlane);

    // The "Start Round with This Flight" button should be visible and enabled
    const startButton = screen.getByRole('button', {
      name: /start round with this flight/i,
    });
    expect(startButton).toBeInTheDocument();
    expect(startButton).not.toBeDisabled();
  });
});

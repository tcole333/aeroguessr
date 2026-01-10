import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PlaneListPanelContent from '../PlaneListPanelContent';
import { StoreContext, createRootStore } from '../../../../store/createRootStore';
import type { PlaneState } from '../../../common/types';
import { webSocketClient } from '../../../../hooks/useWebSocketManager';

function setup(
  planes: PlaneState[] = [],
  { host = 'Me', connected = true } = {},
) {
  const store = createRootStore();
  // Toggle retroMode off (default is true) to test standard mode UI
  store.getState().ui.toggleRetroMode();
  if (planes.length > 0) {
    store.getState().planes.upsertPlanes(planes);
  }
  store.setState((s) => {
    s.game.hostNickname = host;
    s.connection.nickname = 'Me';
    s.connection.playerNickname = 'Me';
  });
  if (connected) {
    store.getState().connection.setStatus('connected');
  }
  const utils = render(
    <StoreContext.Provider value={store}>
      <PlaneListPanelContent />
    </StoreContext.Provider>,
  );
  return { store, ...utils };
}

describe('PlaneListPanelContent', () => {
  it('renders plane items and handles click when host', async () => {
    const plane: PlaneState = {
      hex_ident: 'abc',
      lat: 0,
      lon: 0,
      alt: 1000,
      lat_v: 0,
      lon_v: 0,
      alt_v: 0,
      last_update_ts: 1,
      trail: [],
      origin: 'KBOS', // Flight connected to monitored airport to enable selection
      destination: 'KLAX',
    };
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    setup([plane]);
    const item = screen.getByRole('button', { name: /abc/i });
    expect(item).toBeInTheDocument();

    // Click to expand details
    await userEvent.click(item);

    // Click the combined "Start Round with This Flight" button that appears in the details
    // This button combines select + start in one action for mobile UX
    const startButton = screen.getByRole('button', { name: /start round with this flight/i });
    await userEvent.click(startButton);

    // The combined button sends selectPlane immediately
    expect(sendSpy).toHaveBeenCalledWith({ type: 'selectPlane', payload: { hex: 'abc' } });
    sendSpy.mockRestore();
  });

  it('does not send when not host', async () => {
    const plane: PlaneState = {
      hex_ident: 'abc',
      lat: 0,
      lon: 0,
      alt: 1000,
      lat_v: 0,
      lon_v: 0,
      alt_v: 0,
      last_update_ts: 1,
      trail: [],
    };
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    const { store } = setup([plane], { host: 'Other' });
    const item = screen.getByRole('button', { name: /abc/i });
    await userEvent.click(item);
    expect(sendSpy).not.toHaveBeenCalled();
    expect(store.getState().game.selectedPlaneHex).toBeNull();
    sendSpy.mockRestore();
  });

  it('does not send when disconnected', async () => {
    const plane: PlaneState = {
      hex_ident: 'abc',
      lat: 0,
      lon: 0,
      alt: 1000,
      lat_v: 0,
      lon_v: 0,
      alt_v: 0,
      last_update_ts: 1,
      trail: [],
    };
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    const { store } = setup([plane], { connected: false });
    const item = screen.getByRole('button', { name: /abc/i });
    await userEvent.click(item);
    expect(sendSpy).not.toHaveBeenCalled();
    expect(store.getState().game.selectedPlaneHex).toBeNull();
    sendSpy.mockRestore();
  });

  it('shows placeholder when no planes', () => {
    setup();
    expect(screen.getByText(/scanning for nearby flights/i)).toBeInTheDocument();
  });
});

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
  if (planes.length > 0) {
    store.getState().planes.upsertPlanes(planes);
  }
  store.setState((s) => {
    s.game.hostNickname = host;
    s.connection.nickname = 'Me';
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
    };
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    const { store } = setup([plane]);
    const item = screen.getByRole('button', { name: /abc/i });
    expect(item).toBeInTheDocument();
    await userEvent.click(item);
    expect(sendSpy).toHaveBeenCalledWith({ type: 'selectPlane', payload: { hex: 'abc' } });
    expect(store.getState().game.selectedPlaneHex).toBe('abc');
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

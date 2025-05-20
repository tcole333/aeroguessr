import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import HostControls from '../HostControls';
import { StoreContext, createRootStore } from '../../../../store/createRootStore';
import { webSocketClient } from '../../../../hooks/useWebSocketManager';

function setup({ status = 'connected', host = 'Me', selected = 'abc' } = {}) {
  const store = createRootStore();
  store.getState().connection.setNickname('Me');
  store.getState().connection.setStatus(status as any);
  store.setState((s) => {
    s.game.hostNickname = host;
    s.game.selectedPlaneHex = selected;
  });
  return {
    store,
    ...render(
      <StoreContext.Provider value={store}>
        <HostControls />
      </StoreContext.Provider>,
    ),
  };
}

describe('HostControls', () => {
  it('is hidden when not host', () => {
    setup({ host: 'Other' });
    expect(screen.queryByTestId('host-controls')).toBeNull();
  });

  it('disables buttons when disconnected', () => {
    setup({ status: 'disconnected' });
    expect(screen.getByRole('button', { name: /start round/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /skip round/i })).toBeDisabled();
  });

  it('sends start and skip messages', async () => {
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    setup();
    await userEvent.click(screen.getByRole('button', { name: /start round/i }));
    await userEvent.click(screen.getByRole('button', { name: /skip round/i }));
    expect(sendSpy).toHaveBeenCalledWith({ type: 'startRound', payload: {} });
    expect(sendSpy).toHaveBeenCalledWith({ type: 'skipRound', payload: {} });
    sendSpy.mockRestore();
  });

  it('transfers host and clears input', async () => {
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    setup();
    const input = screen.getByPlaceholderText(/nickname/i);
    await userEvent.type(input, 'Bob');
    await userEvent.click(screen.getByRole('button', { name: /transfer/i }));
    expect(sendSpy).toHaveBeenCalledWith({ type: 'transferHost', payload: { to_nickname: 'Bob' } });
    expect((input as HTMLInputElement).value).toBe('');
    sendSpy.mockRestore();
  });

  it('does not send actions when disconnected', async () => {
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    setup({ status: 'disconnected' });
    await userEvent.click(screen.getByRole('button', { name: /start round/i }));
    await userEvent.type(screen.getByPlaceholderText(/nickname/i), 'Bob');
    await userEvent.click(screen.getByRole('button', { name: /transfer/i }));
    expect(sendSpy).not.toHaveBeenCalled();
    sendSpy.mockRestore();
  });
});

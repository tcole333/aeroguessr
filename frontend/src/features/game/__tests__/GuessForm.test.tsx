import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect } from 'vitest';
import GuessForm from '../components/GuessForm';
import { StoreContext, createRootStore } from '../../../store/createRootStore';
import { webSocketClient } from '../../../hooks/useWebSocketManager';

function setup() {
  const store = createRootStore();
  store.getState().game.setRoundStart({
    hex: 'a',
    timeout_s: 30,
    direction: 'origin',
    round_number: 1,
  });
  store.getState().connection.setStatus('connected');
  return {
    store,
    ...render(
      <StoreContext.Provider value={store}>
        <GuessForm />
      </StoreContext.Provider>,
    ),
  };
}

describe('GuessForm', () => {
  it('submits guess and disables button', async () => {
    const { store } = setup();
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    await userEvent.type(screen.getByLabelText(/airport code/i), 'bos');
    await userEvent.click(screen.getByRole('button', { name: /guess/i }));
    expect(sendSpy).toHaveBeenCalledWith({ type: 'guess', payload: { airport_code: 'BOS' } });
    expect(screen.getByRole('button', { name: /guess/i })).toBeDisabled();
    sendSpy.mockRestore();
  });

  it('shows error on empty submit', async () => {
    setup();
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    await userEvent.click(screen.getByRole('button', { name: /guess/i }));
    expect(sendSpy).not.toHaveBeenCalled();
    expect(screen.getByText(/airport code required/i)).toBeInTheDocument();
    sendSpy.mockRestore();
  });

  it('prevents duplicate submit', async () => {
    setup();
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    await userEvent.type(screen.getByLabelText(/airport code/i), 'bos');
    await userEvent.click(screen.getByRole('button', { name: /guess/i }));
    await userEvent.click(screen.getByRole('button', { name: /guess/i }));
    expect(sendSpy).toHaveBeenCalledTimes(1);
    sendSpy.mockRestore();
  });

  it('resets after round ends', async () => {
    const { store } = setup();
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    await userEvent.type(screen.getByLabelText(/airport code/i), 'bos');
    await userEvent.click(screen.getByRole('button', { name: /guess/i }));
    expect(screen.getByRole('button', { name: /guess/i })).toBeDisabled();
    act(() => {
      store.getState().game.setRoundResult({ results: [], next_host_nickname: null });
    });
    expect(screen.queryByRole('button', { name: /guess/i })).toBeNull();
    sendSpy.mockRestore();
  });

  it('handles send failure', async () => {
    setup();
    const sendSpy = vi
      .spyOn(webSocketClient, 'send')
      .mockImplementation(() => {
        throw new Error('fail');
      });
    await userEvent.type(screen.getByLabelText(/airport code/i), 'bos');
    await userEvent.click(screen.getByRole('button', { name: /guess/i }));
    expect(screen.getByText('fail')).toBeInTheDocument();
    sendSpy.mockRestore();
  });
});

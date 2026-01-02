import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect } from 'vitest';
import GuessForm from '../components/GuessForm';
import { StoreContext, createRootStore } from '../../../store/createRootStore';
import { webSocketClient } from '../../../hooks/useWebSocketManager';

function setup() {
  const store = createRootStore();
  // Toggle retroMode off (default is true) to test standard mode UI
  store.getState().ui.toggleRetroMode();
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
    // Use the aria-label on the input instead of looking for label text
    await userEvent.type(screen.getByLabelText(/airport guess/i), 'bos');
    await userEvent.click(screen.getByRole('button', { name: /submit guess/i }));
    expect(sendSpy).toHaveBeenCalledWith({ type: 'guess', payload: { airport_code: 'BOS' } });
    // After submitting, the button text changes to "Guess Submitted"
    expect(screen.getByRole('button', { name: /guess submitted/i })).toBeDisabled();
    sendSpy.mockRestore();
  });

  it('shows error on empty submit', async () => {
    setup();
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    await userEvent.click(screen.getByRole('button', { name: /submit guess/i }));
    expect(sendSpy).not.toHaveBeenCalled();
    // The error message from useGuess is "Please select or enter an airport code"
    expect(screen.getByText(/please select or enter an airport code/i)).toBeInTheDocument();
    sendSpy.mockRestore();
  });

  it('prevents duplicate submit', async () => {
    setup();
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    await userEvent.type(screen.getByLabelText(/airport guess/i), 'bos');
    await userEvent.click(screen.getByRole('button', { name: /submit guess/i }));
    // Try to click the disabled button (which now shows "Guess Submitted")
    await userEvent.click(screen.getByRole('button', { name: /guess submitted/i }));
    expect(sendSpy).toHaveBeenCalledTimes(1);
    sendSpy.mockRestore();
  });

  it('resets after round ends', async () => {
    const { store } = setup();
    const sendSpy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    await userEvent.type(screen.getByLabelText(/airport guess/i), 'bos');
    await userEvent.click(screen.getByRole('button', { name: /submit guess/i }));
    // After submitting, the button text changes to "Guess Submitted"
    expect(screen.getByRole('button', { name: /guess submitted/i })).toBeDisabled();
    act(() => {
      store.getState().game.setRoundResult({ results: [], next_host_nickname: null });
    });
    // After round ends, the form should be hidden
    expect(screen.queryByRole('button')).toBeNull();
    sendSpy.mockRestore();
  });

  it('handles send failure', async () => {
    setup();
    const sendSpy = vi
      .spyOn(webSocketClient, 'send')
      .mockImplementation(() => {
        throw new Error('fail');
      });
    await userEvent.type(screen.getByLabelText(/airport guess/i), 'bos');
    await userEvent.click(screen.getByRole('button', { name: /submit guess/i }));
    expect(screen.getByText('fail')).toBeInTheDocument();
    sendSpy.mockRestore();
  });
});

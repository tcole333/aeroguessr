import React from 'react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import { StoreContext, createRootStore } from '../../../store/createRootStore';
import { useGuess } from '../hooks/useGuess';
import { webSocketClient } from '../../../hooks/useWebSocketManager';

function wrapper(store: ReturnType<typeof createRootStore>) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <StoreContext.Provider value={store}>{children}</StoreContext.Provider>;
  };
}

describe('useGuess', () => {
  it('submits and resets on round change', async () => {
    const store = createRootStore();
    store.getState().connection.setStatus('connected');
    const { result, rerender } = renderHook(() => useGuess(), {
      wrapper: wrapper(store),
    });

    act(() => {
      store.getState().game.setRoundStart({
        hex: 'a',
        timeout_s: 30,
        direction: 'origin',
        round_number: 1,
      });
    });
    rerender();

    act(() => result.current.setInputValue('bos'));
    const spy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});

    act(() => result.current.handleSubmit({ preventDefault() {} } as any));
    expect(spy).toHaveBeenCalledWith({ type: 'guess', payload: { airport_code: 'BOS' } });
    expect(result.current.disabled).toBe(true);

    act(() => {
      store.getState().game.setRoundResult({ results: [], next_host_nickname: null });
    });
    rerender();

    await waitFor(() => expect(result.current.disabled).toBe(false));
    spy.mockRestore();
  });

  function renderDuringRound(store = createRootStore()) {
    store.getState().connection.setStatus('connected');
    const { result, rerender } = renderHook(() => useGuess(), {
      wrapper: wrapper(store),
    });
    act(() => {
      store.getState().game.setRoundStart({
        hex: 'a',
        timeout_s: 30,
        direction: 'origin',
        round_number: 1,
      });
    });
    rerender();
    return result;
  }

  const submitEvent = { preventDefault() {} } as React.FormEvent<HTMLFormElement>;

  it('rejects a typed code that is not in the airport dataset without sending', () => {
    const result = renderDuringRound();
    const spy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});

    act(() => result.current.setInputValue('zzz'));
    act(() => result.current.handleSubmit(submitEvent));

    expect(result.current.error).toContain("Unknown airport code 'ZZZ'");
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it('sends a typed ICAO code from the airport dataset', () => {
    const result = renderDuringRound();
    const spy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});

    act(() => result.current.setInputValue(' kord '));
    act(() => result.current.handleSubmit(submitEvent));

    expect(spy).toHaveBeenCalledWith({ type: 'guess', payload: { airport_code: 'KORD' } });
    spy.mockRestore();
  });

  it('lets the player guess again once the server refuses a guess', () => {
    const store = createRootStore();
    const result = renderDuringRound(store);
    const spy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    act(() => result.current.setInputValue('bos'));
    act(() => result.current.handleSubmit(submitEvent));

    act(() => store.getState().game.setGuessRejection("Unknown airport code 'BOS'."));

    expect([result.current.disabled, result.current.error]).toEqual([
      false,
      "Unknown airport code 'BOS'.",
    ]);
    spy.mockRestore();
  });

  it('keeps a refusal a newer guess replaced out of a guess form opened later', () => {
    const store = createRootStore();
    const result = renderDuringRound(store);
    const spy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});
    act(() => store.getState().game.setGuessRejection("Unknown airport code 'BOS'."));
    act(() => result.current.setInputValue('ord'));
    act(() => result.current.handleSubmit(submitEvent));

    const { result: laterForm } = renderHook(() => useGuess(), { wrapper: wrapper(store) });

    expect(laterForm.current.error).toBeNull();
    spy.mockRestore();
  });
});

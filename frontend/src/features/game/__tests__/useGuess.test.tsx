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

    act(() => result.current.setCode('bos'));
    const spy = vi.spyOn(webSocketClient, 'send').mockImplementation(() => {});

    act(() => result.current.handleSubmit({ preventDefault() {} } as any));
    expect(spy).toHaveBeenCalled();
    expect(result.current.disabled).toBe(true);

    act(() => {
      store.getState().game.setRoundResult({ results: [], next_host_nickname: null });
    });
    rerender();

    await waitFor(() => expect(result.current.disabled).toBe(false));
  });
});

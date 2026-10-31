import React from 'react';
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useAutoRejoin } from '../useAutoRejoin';
import { StoreContext, createRootStore, type RootStore } from '../../store/createRootStore';

/** Saves a session as the previous page did, so the next store loads it, as after a refresh. */
function saveSession(view: 'home' | 'game'): void {
  const previousPage = createRootStore().getState();
  previousPage.connection.setConnectionDetails({
    roomCode: 'ABCD',
    wsUrl: 'ws://localhost/api/v0/rooms/ws/ABCD/Ann',
    nickname: 'Ann',
  });
  previousPage.ui.setCurrentView(view);
}

function renderAutoRejoin(store: RootStore) {
  return renderHook(() => useAutoRejoin(), {
    wrapper: ({ children }: { children: React.ReactNode }) => (
      <StoreContext.Provider value={store}>{children}</StoreContext.Provider>
    ),
  });
}

describe('useAutoRejoin', () => {
  it('flags a rejoin when a refresh lands back in the game', () => {
    saveSession('game');
    const store = createRootStore();

    renderAutoRejoin(store);

    const { isRejoinAttempt, roomCode } = store.getState().connection;
    expect({ isRejoinAttempt, roomCode }).toEqual({ isRejoinAttempt: true, roomCode: 'ABCD' });
  });

  it('forgets a saved room when the page opens on home', () => {
    saveSession('home');
    const store = createRootStore();

    renderAutoRejoin(store);

    const { isRejoinAttempt, roomCode, wsUrl, nickname } = store.getState().connection;
    expect({ isRejoinAttempt, roomCode, wsUrl, nickname }).toEqual({
      isRejoinAttempt: false,
      roomCode: null,
      wsUrl: null,
      nickname: null,
    });
  });

  it('does not flag a rejoin for a saved game view without a room', () => {
    createRootStore().getState().ui.setCurrentView('game');
    const store = createRootStore();

    renderAutoRejoin(store);

    expect(store.getState().connection.isRejoinAttempt).toBe(false);
  });
});

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MobileStatusBar } from './MobileStatusBar';
import { StoreContext, createRootStore, type RootStore } from '../../store/createRootStore';

/** What the join forms store once the REST call returns, before the socket opens. */
function enterRoom(store: RootStore, roomCode: string): void {
  store.getState().connection.setConnectionDetails({
    roomCode,
    wsUrl: `ws://localhost/api/v0/rooms/ws/${roomCode}/Ann`,
    nickname: 'Ann',
  });
}

function joinRoom(store: RootStore, roomCode: string, isSolo: boolean): void {
  enterRoom(store, roomCode);
  store.getState().game.hydrate({
    room_meta: { is_solo: isSolo, host_nickname: isSolo ? 'Ann' : 'Bob', mode: 'Exact' },
    players: { Ann: { score: 120 }, ...(isSolo ? {} : { Bob: { score: 80 } }) },
  });
}

function renderStatusBar(store: RootStore) {
  return render(
    <StoreContext.Provider value={store}>
      <MobileStatusBar />
    </StoreContext.Provider>,
  );
}

describe('MobileStatusBar', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('shows the room code, mode, own score and host in a multiplayer room', () => {
    const store = createRootStore();
    joinRoom(store, 'ABCD', false);

    renderStatusBar(store);

    expect(screen.getByText('ABCD')).toBeInTheDocument();
    expect(screen.getByText('Exact')).toBeInTheDocument();
    expect(screen.getByText('120 pts')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });

  it('labels a solo room Solo and leaves out its code and host', () => {
    const store = createRootStore();
    joinRoom(store, 'solo:ab12cd34', true);

    renderStatusBar(store);

    expect(screen.getByText('Solo')).toBeInTheDocument();
    expect(screen.getByText('120 pts')).toBeInTheDocument();
    expect(screen.queryByText('solo:ab12cd34')).not.toBeInTheDocument();
    expect(screen.queryByText('Ann')).not.toBeInTheDocument();
  });

  it('labels a solo room Solo before its stateSync arrives', () => {
    const store = createRootStore();
    enterRoom(store, 'solo:ab12cd34');

    renderStatusBar(store);

    expect(screen.getByText('Solo')).toBeInTheDocument();
    expect(screen.queryByText('solo:ab12cd34')).not.toBeInTheDocument();
  });
});

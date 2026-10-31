import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { RoomCodeDisplay } from './RoomCodeDisplay';
import { StoreContext, createRootStore, type RootStore } from '../../store/createRootStore';

const writeText = vi.fn();
Object.assign(navigator, { clipboard: { writeText } });

/** What the join forms store once the REST call returns, before the socket opens. */
function enterRoom(store: RootStore, roomCode: string): void {
  store.getState().connection.setConnectionDetails({
    roomCode,
    wsUrl: `ws://localhost/api/v0/rooms/ws/${roomCode}/Ann`,
    nickname: 'Ann',
  });
}

/** The stateSync the server sends once the socket opens. */
function receiveStateSync(store: RootStore, isSolo: boolean): void {
  store.getState().game.hydrate({
    room_meta: { is_solo: isSolo, host_nickname: 'Ann' },
    players: { Ann: { score: 0 } },
  });
}

function joinRoom(store: RootStore, roomCode: string, isSolo: boolean): void {
  enterRoom(store, roomCode);
  receiveStateSync(store, isSolo);
}

function renderDisplay(store: RootStore, className?: string) {
  return render(
    <StoreContext.Provider value={store}>
      <RoomCodeDisplay className={className} />
    </StoreContext.Provider>,
  );
}

describe('RoomCodeDisplay', () => {
  beforeEach(() => {
    localStorage.clear();
    writeText.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the code of a multiplayer room', () => {
    const store = createRootStore();
    joinRoom(store, 'ABCD', false);

    renderDisplay(store);

    expect(screen.getByText('Room:')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /room code abcd/i })).toHaveTextContent('ABCD');
  });

  it('shows nothing in a solo room, whose code is not for sharing', () => {
    const store = createRootStore();
    joinRoom(store, 'solo:ab12cd34', true);

    const { container } = renderDisplay(store);

    expect(container).toBeEmptyDOMElement();
  });

  it('shows nothing in a solo room before its stateSync arrives', () => {
    const store = createRootStore();
    enterRoom(store, 'solo:ab12cd34');

    const { container } = renderDisplay(store);

    expect(container).toBeEmptyDOMElement();
  });

  it('shows the code of a room joined after leaving a solo game', () => {
    const store = createRootStore();
    joinRoom(store, 'solo:ab12cd34', true);
    store.getState().game.leaveRoom();
    joinRoom(store, 'WXYZ', false);

    renderDisplay(store);

    expect(screen.getByRole('button', { name: /room code wxyz/i })).toBeInTheDocument();
  });

  it('shows nothing before joining a room', () => {
    const { container } = renderDisplay(createRootStore());

    expect(container).toBeEmptyDOMElement();
  });

  it('copies the code and confirms for two seconds', async () => {
    vi.useFakeTimers();
    writeText.mockResolvedValueOnce(undefined);
    const store = createRootStore();
    joinRoom(store, 'ABCD', false);
    renderDisplay(store);

    fireEvent.click(screen.getByRole('button', { name: /room code abcd/i }));
    await act(async () => {});

    expect(writeText).toHaveBeenCalledWith('ABCD');
    act(() => vi.advanceTimersByTime(1999));
    expect(screen.getByText('Copied!')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByText('Copied!')).not.toBeInTheDocument();
  });

  it('reports a failed copy without confirming it', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    writeText.mockRejectedValueOnce(new Error('Clipboard error'));
    const store = createRootStore();
    joinRoom(store, 'ABCD', false);
    renderDisplay(store);

    fireEvent.click(screen.getByRole('button', { name: /room code abcd/i }));
    await act(async () => {});

    expect(consoleError).toHaveBeenCalledWith('Failed to copy room code:', expect.any(Error));
    expect(screen.queryByText('Copied!')).not.toBeInTheDocument();
    consoleError.mockRestore();
  });

  it('passes its className to the wrapper', () => {
    const store = createRootStore();
    joinRoom(store, 'ABCD', false);

    const { container } = renderDisplay(store, 'custom-class');

    expect(container.firstChild).toHaveClass('custom-class');
  });
});

import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Toaster } from 'sonner';
import { StoreContext, createRootStore } from '../../store/createRootStore';
import { useWebSocketManager, webSocketClient as client } from '../useWebSocketManager';
import GuessForm from '../../features/game/components/GuessForm';
import PlaneDetails from '../../features/planes/components/PlaneDetails';
import { FakeWebSocket } from '../../mocks/fakeWebSocket';

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
  // Destroy the singleton client after each test to reset its internal state
  if (client && typeof client.destroy === 'function') {
    client.destroy();
  }
});

describe('useWebSocketManager', () => {
  let wrapperStore: ReturnType<typeof createRootStore>;
  function Wrapper({ children }: { children: React.ReactNode }) {
    wrapperStore = createRootStore();
    return (
      <StoreContext.Provider value={wrapperStore}>{children}</StoreContext.Provider>
    );
  }

  it('updates connection status', () => {
    function Test() {
      useWebSocketManager('ROOM', 'Nick');
      return null;
    }
    render(<Test />, { wrapper: Wrapper });
    const socket = FakeWebSocket.latest();
    const store = wrapperStore;
    // connecting immediately
    expect(store.getState().connection.status).toBe('connecting');
    socket.serverAccepts();
    expect(store.getState().connection.status).toBe('connected');
  });

  it('processes game messages', async () => {
    function Test() {
      useWebSocketManager('ROOM', 'Nick');
      return null;
    }
    render(<Test />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(FakeWebSocket.instances.length).toBeGreaterThan(0);
    });

    const socket = FakeWebSocket.latest();
    const store = wrapperStore;
    socket.serverAccepts();

    socket.serverSends({
      type: 'stateSync',
      payload: { room_meta: null, players: { A: { nickname: 'A', score: 3 } } },
    });
    expect(store.getState().game.scores).toEqual({ A: 3 });

    const plane = {
      hex_ident: 'a',
      lat: 0,
      lon: 0,
      alt: 0,
      lat_v: 0,
      lon_v: 0,
      alt_v: 0,
      last_update_ts: 1,
      trail: [[0, 0, 0]],
      first_seen_ts: 1,
      update_count: 1,
      route_hint: { guess_direction: null, known_airport: null, eligible: false },
    };
    socket.serverSends({
      type: 'delta',
      payload: {
        planes: { updated: [plane] },
        scores: { A: 5 },
        round: { state: 'x', round_number: 1 },
      },
    });
    expect(store.getState().planes.values.a).toBeDefined();
    expect(store.getState().game.scores.A).toBe(5);

    socket.serverSends({
      type: 'roundStart',
      payload: { hex: 'a', timeout_s: 30, direction: 'origin', round_number: 2 },
    });
    expect(store.getState().game.roundTimeout).toBe(30);

    socket.serverSends({
      type: 'roundResult',
      payload: {
        results: [
          {
            nickname: 'A',
            guess: 'BOS',
            correct_code: 'BOS',
            score_awarded: 100,
            current_total_score: 105,
          },
        ],
        next_host_nickname: null,
      },
    });
    expect(store.getState().game.round).toBeNull();
    expect(store.getState().game.scores.A).toBe(105);
  });

  it('handles playerJoined message', async () => {
    function Test() {
      useWebSocketManager('ROOM', 'ExistingPlayer');
      return null;
    }
    render(<Test />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(FakeWebSocket.instances.length).toBeGreaterThan(0);
    });

    const socket = FakeWebSocket.latest();
    const store = wrapperStore;
    socket.serverAccepts();

    // Trigger playerJoined message
    socket.serverSends({
      type: 'playerJoined',
      payload: { nickname: 'NewPlayer' },
    });

    expect(store.getState().game.scores['NewPlayer']).toBe(0);
  });

  it('handles playerLeft message', async () => {
    function Test() {
      useWebSocketManager('ROOM', 'Nick');
      return null;
    }
    render(<Test />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(FakeWebSocket.instances.length).toBeGreaterThan(0);
    });

    const socket = FakeWebSocket.latest();
    const store = wrapperStore;
    socket.serverAccepts();

    // First add players via stateSync
    socket.serverSends({
      type: 'stateSync',
      payload: {
        room_meta: null,
        players: {
          Player1: { nickname: 'Player1', score: 50 },
          Player2: { nickname: 'Player2', score: 30 }
        }
      },
    });

    expect(store.getState().game.scores).toEqual({ Player1: 50, Player2: 30 });

    // Trigger playerLeft message
    socket.serverSends({
      type: 'playerLeft',
      payload: { nickname: 'Player1' },
    });

    expect(store.getState().game.scores).toEqual({ Player2: 30 });
  });

  it('handles newHost message', async () => {
    function Test() {
      useWebSocketManager('ROOM', 'Nick');
      return null;
    }
    render(<Test />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(FakeWebSocket.instances.length).toBeGreaterThan(0);
    });

    const socket = FakeWebSocket.latest();
    const store = wrapperStore;
    socket.serverAccepts();

    // Set initial host
    socket.serverSends({
      type: 'stateSync',
      payload: {
        room_meta: { mode: 'Exact', round_timeout_seconds: 30, host_nickname: 'OldHost' },
        players: {}
      },
    });
    expect(store.getState().game.hostNickname).toBe('OldHost');

    // Trigger newHost message
    socket.serverSends({
      type: 'newHost',
      payload: { nickname: 'NewHost' },
    });

    expect(store.getState().game.hostNickname).toBe('NewHost');
  });
});

describe('useWebSocketManager server errors', () => {
  function renderConnected(children?: React.ReactNode) {
    const store = createRootStore();
    function Test() {
      useWebSocketManager('ROOM', 'Nick');
      return null;
    }
    render(
      <StoreContext.Provider value={store}>
        <Toaster />
        <Test />
        {children}
      </StoreContext.Provider>,
    );
    const socket = FakeWebSocket.latest();
    act(() => socket.serverAccepts());
    return { socket, store };
  }

  function serverError(code: string, message: string) {
    return { type: 'error', payload: { code, message } };
  }

  it.each([
    ['PLANE_DATA_INCOMPLETE_FOR_GUESS', "This flight's origin airport isn't in the game's airport list. Pick another flight."],
    ['INVALID_PLANE_SELECTION', 'Flight must be departing from or arriving at KBOS.'],
    ['INVALID_STATE_FOR_ACTION', "The last round just ended. You can start the next one in a few seconds."],
  ])('shows a %s rejection as a toast with the server message', async (code, message) => {
    const { socket } = renderConnected();

    socket.serverSends(serverError(code, message));

    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it('shows one toast when the same error repeats', async () => {
    const { socket } = renderConnected();
    const repeated = serverError('INVALID_STATE_FOR_ACTION', 'A round is already in progress.');

    socket.serverSends(repeated);
    socket.serverSends(repeated);
    // Toasts render in arrival order, so once this one shows, both repeats have been handled
    socket.serverSends(serverError('NOT_HOST', 'Only the host can start the round.'));
    await screen.findByText('Only the host can start the round.');

    expect(screen.getAllByText('A round is already in progress.')).toHaveLength(1);
  });

  it('shows a generic toast for an error without a payload', async () => {
    const { socket } = renderConnected();

    socket.serverSends({ type: 'error' });

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument();
  });

  const unknownAirport = "Unknown airport code 'BOS'. Enter an IATA (ORD) or ICAO (KORD) code.";

  it('shows an unknown airport refusal in the guess form and lets the player guess again', async () => {
    const { socket, store } = renderConnected(<GuessForm />);
    act(() => {
      store.getState().ui.toggleRetroMode();
      store.getState().game.setRoundStart({ hex: 'a', timeout_s: 30, direction: 'origin', round_number: 1 });
    });
    await userEvent.type(screen.getByLabelText(/airport guess/i), 'bos');
    await userEvent.click(screen.getByRole('button', { name: /submit guess/i }));

    act(() => socket.serverSends(serverError('UNKNOWN_AIRPORT_CODE', unknownAirport)));

    expect(screen.getByRole('alert')).toHaveTextContent(unknownAirport);
    expect(screen.getByRole('button', { name: /submit guess/i })).toBeEnabled();
  });

  it('does not show an unknown airport refusal as a toast', async () => {
    const { socket } = renderConnected();

    socket.serverSends(serverError('UNKNOWN_AIRPORT_CODE', unknownAirport));
    socket.serverSends(serverError('NOT_HOST', 'Only the host can start the round.'));
    await screen.findByText('Only the host can start the round.');

    expect(screen.queryByText(unknownAirport)).not.toBeInTheDocument();
  });

  it('starts the round once the server confirms the selection', async () => {
    const { socket, store } = renderConnected(<PlaneDetails hex="abc123" onClose={() => {}} />);
    act(() => {
      store.getState().planes.upsertPlanes([
        {
          hex_ident: 'abc123',
          lat: 42.36,
          lon: -71.01,
          alt: 10000,
          lat_v: 0,
          lon_v: 0,
          alt_v: 0,
          last_update_ts: 1,
          trail: [],
          route_hint: { guess_direction: 'destination', known_airport: 'KBOS', eligible: true },
        },
      ]);
      store.setState((s) => {
        s.game.hostNickname = 'Nick';
        s.connection.nickname = 'Nick';
      });
    });
    await userEvent.click(screen.getByRole('button', { name: /start round with this flight/i }));

    act(() =>
      socket.serverSends({
        type: 'planeSelectedConfirm',
        payload: { hex: 'abc123', guess_direction: 'destination' },
      }),
    );

    expect(socket.sentTypes()).toEqual(['selectPlane', 'startRound']);
  });
});

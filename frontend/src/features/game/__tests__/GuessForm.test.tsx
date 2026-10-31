import React from 'react';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import GuessForm from '../components/GuessForm';
import { StoreContext, createRootStore } from '../../../store/createRootStore';
import { useWebSocketManager, webSocketClient } from '../../../hooks/useWebSocketManager';
import { FakeWebSocket } from '../../../mocks/fakeWebSocket';
import type { RouteHint } from '../../common/types';

const DEPARTING_BOS: RouteHint = { guess_direction: 'destination', known_airport: 'KBOS', eligible: true };
const ARRIVING_BOS: RouteHint = { guess_direction: 'origin', known_airport: 'KBOS', eligible: true };
const OVERFLIGHT: RouteHint = { guess_direction: null, known_airport: null, eligible: false };

function InRoom({ children }: { children: React.ReactNode }) {
  useWebSocketManager('ABCD', 'Ann');
  return <>{children}</>;
}

/** Renders the form in room ABCD and has the server accept the connection; the socket plays the server. */
function renderInRoom({ retroMode = false } = {}) {
  const store = createRootStore();
  if (!retroMode) store.getState().ui.toggleRetroMode();
  render(
    <StoreContext.Provider value={store}>
      <InRoom>
        <GuessForm />
      </InRoom>
    </StoreContext.Provider>,
  );
  const socket = FakeWebSocket.latest();
  act(() => socket.serverAccepts());
  return socket;
}

function serverSends(socket: FakeWebSocket, message: unknown) {
  act(() => socket.serverSends(message));
}

function startRound(socket: FakeWebSocket, direction: 'origin' | 'destination' = 'destination') {
  serverSends(socket, {
    type: 'roundStart',
    payload: { hex: 'abc123', timeout_s: 30, direction, round_number: 1 },
  });
}

function sendPlane(socket: FakeWebSocket, plane: { route_hint: RouteHint; alt_v?: number; alt?: number }) {
  serverSends(socket, {
    type: 'delta',
    payload: {
      planes: {
        updated: [
          {
            hex_ident: 'abc123',
            lat: 42.36,
            lon: -71.06,
            alt: 10000,
            lat_v: 0,
            lon_v: 0,
            alt_v: 0,
            last_update_ts: 1,
            trail: [],
            callsign: 'UAL123',
            first_seen_ts: 1,
            update_count: 1,
            ...plane,
          },
        ],
      },
    },
  });
}

function guessesSent(socket: FakeWebSocket) {
  return socket.sent.filter((frame) => frame.type === 'guess');
}

async function guess(code: string) {
  await userEvent.type(screen.getByRole('combobox', { name: /airport guess/i }), code);
  await userEvent.click(screen.getByRole('button', { name: /submit guess/i }));
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
  webSocketClient.destroy();
});

describe('GuessForm', () => {
  it('opens when a round starts', () => {
    const socket = renderInRoom();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    startRound(socket);

    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByRole('combobox', { name: /airport guess/i })).toHaveAttribute('id', 'airport-guess');
  });

  it.each([
    ['origin', /guess the origin/i],
    ['destination', /guess the destination/i],
  ] as const)("asks for the round's %s, with the seconds left", (direction, prompt) => {
    const socket = renderInRoom();

    startRound(socket, direction);

    expect(screen.getByText(prompt)).toHaveTextContent('(30)');
  });

  it('sends the typed code and locks the form', async () => {
    const socket = renderInRoom();
    startRound(socket);

    await guess('bos');

    expect(guessesSent(socket)).toEqual([{ type: 'guess', payload: { airport_code: 'BOS' } }]);
    expect(screen.getByRole('button', { name: /guess submitted/i })).toBeDisabled();
    expect(screen.getByRole('combobox', { name: /airport guess/i })).toBeDisabled();
  });

  it('sends the code of an airport picked from the suggestions', async () => {
    const socket = renderInRoom();
    startRound(socket);

    await userEvent.type(screen.getByRole('combobox', { name: /airport guess/i }), 'Kennedy');
    await userEvent.click(await screen.findByRole('option', { name: /john f kennedy/i }));

    expect(screen.getByText('Selected: John F Kennedy International Airport (JFK)')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /submit guess/i }));
    expect(guessesSent(socket)).toEqual([{ type: 'guess', payload: { airport_code: 'JFK' } }]);
  });

  it('asks for a code instead of sending an empty guess', async () => {
    const socket = renderInRoom();
    startRound(socket);

    await userEvent.click(screen.getByRole('button', { name: /submit guess/i }));

    expect(guessesSent(socket)).toEqual([]);
    expect(screen.getByRole('alert')).toHaveTextContent('Please select or enter an airport code');
    expect(screen.getByRole('combobox', { name: /airport guess/i })).toHaveAttribute('aria-describedby', 'guess-error');
  });

  it('sends one guess however often the button is clicked', async () => {
    const socket = renderInRoom();
    startRound(socket);

    await guess('bos');
    await userEvent.click(screen.getByRole('button', { name: /guess submitted/i }));

    expect(guessesSent(socket)).toHaveLength(1);
  });

  it('closes when the round ends', async () => {
    const socket = renderInRoom();
    startRound(socket);
    await guess('bos');

    serverSends(socket, { type: 'roundResult', payload: { hex: 'abc123', results: [], next_host_nickname: null } });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows a failed send and lets the player try again', async () => {
    const socket = renderInRoom();
    startRound(socket);
    vi.spyOn(socket, 'send').mockImplementationOnce(() => {
      throw new Error('fail');
    });

    await guess('bos');
    expect(screen.getByRole('alert')).toHaveTextContent('fail');
    await userEvent.click(screen.getByRole('button', { name: /submit guess/i }));

    expect(guessesSent(socket)).toEqual([{ type: 'guess', payload: { airport_code: 'BOS' } }]);
  });

  it('closes on a backdrop click before a guess', async () => {
    const socket = renderInRoom();
    startRound(socket);

    await userEvent.click(screen.getByRole('dialog'));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('stays open on a backdrop click after a guess', async () => {
    const socket = renderInRoom();
    startRound(socket);
    await guess('bos');

    await userEvent.click(screen.getByRole('dialog'));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('stays open when the form itself is clicked', async () => {
    const socket = renderInRoom();
    startRound(socket);

    await userEvent.click(screen.getByText(/guess the destination/i));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  describe('in retro mode', () => {
    it.each([
      ['DEPARTING', 'a departure from the monitored airport', DEPARTING_BOS, 0, 10000],
      ['ARRIVING', 'an arrival at the monitored airport', ARRIVING_BOS, 0, 10000],
      ['DEPARTING', 'a descending departure', DEPARTING_BOS, -500, 5000],
      ['ARRIVING', 'a climbing arrival', ARRIVING_BOS, 500, 5000],
      ['ASCENDING', 'a climbing overflight', OVERFLIGHT, 500, 15000],
      ['DESCENDING', 'a descending overflight', OVERFLIGHT, -500, 10000],
      ['CRUISING', 'an overflight in level flight', OVERFLIGHT, 50, 35000],
      ['CRUISING', 'an overflight holding its altitude exactly', OVERFLIGHT, 0, 35000],
      ['TRACKING', 'an overflight without altitude data', OVERFLIGHT, 0, 0],
    ])('shows %s for %s', (status, _description, routeHint, altV, alt) => {
      const socket = renderInRoom({ retroMode: true });
      sendPlane(socket, { route_hint: routeHint, alt_v: altV, alt });

      startRound(socket);

      expect(screen.getByText('UAL123')).toBeInTheDocument();
      expect(screen.getByText(status)).toBeInTheDocument();
    });

    it('shows only the monitored end of a departure while its destination is guessed', () => {
      const socket = renderInRoom({ retroMode: true });
      sendPlane(socket, { route_hint: DEPARTING_BOS });

      startRound(socket, 'destination');

      expect(screen.getByText('Origin').nextElementSibling?.textContent).toBe('Boston');
      expect(screen.queryByText('Destination')).not.toBeInTheDocument();
    });
  });
});

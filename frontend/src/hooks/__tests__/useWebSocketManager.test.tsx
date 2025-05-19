import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { StoreContext, createRootStore } from '../../store/createRootStore';
import { useWebSocketManager } from '../useWebSocketManager';

class MockSocket {
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) {}
  send(data: string) { this.sent.push(data); }
  close() { this.readyState = MockSocket.OPEN; }
  triggerOpen() { this.readyState = MockSocket.OPEN; this.onopen?.(); }
  triggerMessage(data: any) { this.onmessage?.({ data: JSON.stringify(data) }); }
  triggerClose() { this.onclose?.(); }
  addEventListener(event: string, cb: any) {
    switch (event) {
      case 'open':
        this.onopen = cb;
        break;
      case 'message':
        this.onmessage = cb;
        break;
      case 'close':
        this.onclose = cb;
        break;
      case 'error':
        this.onerror = cb;
        break;
      default:
        break;
    }
  }
}

let OriginalWebSocket: any;
let sockets: MockSocket[] = [];

beforeEach(() => {
  OriginalWebSocket = global.WebSocket;
  sockets = [];
  const stub: any = vi.fn((url: string) => {
    const s = new MockSocket(url);
    sockets.push(s);
    return s;
  });
  stub.OPEN = 1;
  vi.stubGlobal('WebSocket', stub);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useWebSocketManager', () => {
  let wrapperStore: ReturnType<typeof createRootStore>;
  function Wrapper({ children }: { children: React.ReactNode }) {
    wrapperStore = createRootStore();
    return (
      <StoreContext.Provider value={wrapperStore}>{children}</StoreContext.Provider>
    );
  }

  it('updates connection status and heartbeat', () => {
    function Test() {
      useWebSocketManager('ROOM', 'Nick');
      return null;
    }
    render(<Test />, { wrapper: Wrapper });
    const socket = sockets[0];
    const store = wrapperStore;
    // connecting immediately
    expect(store.getState().connection.status).toBe('connecting');
    socket.triggerOpen();
    expect(store.getState().connection.status).toBe('connected');
    socket.triggerMessage({ type: 'pong', payload: { seq: Date.now() } });
    expect(store.getState().connection.lastHeartbeat).not.toBeNull();
  });

  it('processes game messages', () => {
    function Test() {
      useWebSocketManager('ROOM', 'Nick');
      return null;
    }
    render(<Test />, { wrapper: Wrapper });
    const socket = sockets[0];
    const store = wrapperStore;
    socket.triggerOpen();

    socket.triggerMessage({
      type: 'stateSync',
      payload: { room_meta: null, players: { A: {} } },
    });
    expect(store.getState().game.players).toEqual({ A: {} });

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
    };
    socket.triggerMessage({
      type: 'delta',
      payload: {
        planes: { updated: [plane] },
        scores: { A: 5 },
        round: { state: 'x', round_number: 1 },
      },
    });
    expect(store.getState().planes.values.a).toBeDefined();
    expect(store.getState().game.scores.A).toBe(5);

    socket.triggerMessage({
      type: 'roundStart',
      payload: { hex: 'a', timeout_s: 30, direction: 'origin', round_number: 2 },
    });
    expect(store.getState().game.roundTimeout).toBe(30);

    socket.triggerMessage({
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
});

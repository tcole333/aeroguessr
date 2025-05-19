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
});

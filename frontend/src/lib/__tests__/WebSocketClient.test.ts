import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createWebSocketClient, resolveWsBaseUrl } from '../WebSocketClient';
import { InboundMessage } from '../../../types/ws';

class MockSocket {
  static OPEN = 1;
  static CLOSED = 3;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) {}
  send(data: string) { this.sent.push(data); }
  close() { this.readyState = MockSocket.CLOSED; }
  triggerOpen() { this.readyState = MockSocket.OPEN; this.onopen?.(); }
  triggerMessage(data: any) { this.onmessage?.({ data: JSON.stringify(data) }); }
  triggerClose(code = 1000, reason = 'normal') {
    this.readyState = MockSocket.CLOSED;
    this.onclose?.({ code, reason } as any);
  }
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
  stub.CLOSED = 3;
  vi.stubGlobal('WebSocket', stub);
  vi.useFakeTimers();
  vi.spyOn(Math, "random").mockReturnValue(0);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});


describe('WebSocketClient', () => {
  it('prefers the configured WebSocket base URL when present', () => {
    expect(resolveWsBaseUrl({
      envBaseUrl: 'wss://example.com',
      browserOrigin: 'https://fallback.example.com',
    })).toBe('wss://example.com');
  });

  it('falls back to the browser origin when no WebSocket env override is set', () => {
    expect(resolveWsBaseUrl({ browserOrigin: 'https://example.com' })).toBe(
      'https://example.com',
    );
  });

  it('emits connected and flushes queue', () => {
    const client = createWebSocketClient('ws://test');
    const msgs: InboundMessage[] = [];
    client.subscribe((m) => msgs.push(m));
    client.send({ type: 'ping' });
    client.connect('ROOM', 'Nick');
    const socket = sockets[0];
    socket.triggerOpen();
    expect(socket.sent.length).toBe(1);
    expect(msgs.length).toBe(0);
  });

  it('reconnects on close with backoff', () => {
    const client = createWebSocketClient('ws://test');
    client.connect('A', 'B');
    const socket = sockets[0];
    socket.triggerOpen();
    socket.triggerClose();
    vi.advanceTimersByTime(600);
    expect(sockets.length).toBe(2);
  });

  it('parses valid messages and ignores invalid', () => {
    const client = createWebSocketClient('ws://test');
    const msgs: InboundMessage[] = [];
    client.subscribe((m) => msgs.push(m));
    client.connect('A', 'B');
    const socket = sockets[0];
    socket.triggerOpen();

    // Send a valid message that should be emitted (e.g., an error message)
    const validEmittedMessage = {
      type: 'error' as const,
      payload: { code: 'UNKNOWN_ERROR' as const, message: 'test error' }
    };
    socket.triggerMessage(validEmittedMessage);

    // Send an invalid message (has structure but invalid type)
    socket.triggerMessage({ type: 'invalidType', payload: {} });

    expect(msgs.length).toBe(1);
    expect(msgs[0].type).toBe('error');
    if (msgs[0].type === 'error') {
      expect(msgs[0].payload?.message).toBe('test error');
    }
  });

  it('does not reconnect after intentional destroy', () => {
    const client = createWebSocketClient('ws://test');
    client.connect('A', 'B');
    const socket = sockets[0];
    socket.triggerOpen();

    // Call destroy which should set isIntentionalClose flag
    client.destroy();

    // Trigger the close event (this happens when socket.close() is called)
    socket.triggerClose();

    // Advance timers - should NOT create a new connection
    vi.advanceTimersByTime(5000);

    // Should still only have 1 socket (no reconnection)
    expect(sockets.length).toBe(1);
  });
});

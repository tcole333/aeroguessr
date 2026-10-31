import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createWebSocketClient } from '../WebSocketClient';
import { InboundMessage } from '../../../types/ws';
import { FakeWebSocket } from '../../mocks/fakeWebSocket';

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
  vi.useFakeTimers();
  vi.spyOn(Math, "random").mockReturnValue(0);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});


describe('WebSocketClient', () => {
  it('emits connected and flushes queue', () => {
    const client = createWebSocketClient('ws://test');
    const msgs: InboundMessage[] = [];
    client.subscribe((m) => msgs.push(m));
    client.send({ type: 'ping' });
    client.connect('ROOM', 'Nick');
    const socket = FakeWebSocket.latest();
    socket.serverAccepts();
    expect(socket.sent).toEqual([{ type: 'ping' }]);
    expect(msgs.length).toBe(0);
  });

  it('reconnects on close with backoff', () => {
    const client = createWebSocketClient('ws://test');
    client.connect('A', 'B');
    const socket = FakeWebSocket.latest();
    socket.serverAccepts();
    socket.serverCloses();
    vi.advanceTimersByTime(600);
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it('parses valid messages and ignores invalid', () => {
    const client = createWebSocketClient('ws://test');
    const msgs: InboundMessage[] = [];
    client.subscribe((m) => msgs.push(m));
    client.connect('A', 'B');
    const socket = FakeWebSocket.latest();
    socket.serverAccepts();

    // Send a valid message that should be emitted (e.g., an error message)
    const validEmittedMessage = {
      type: 'error' as const,
      payload: { code: 'UNKNOWN_ERROR' as const, message: 'test error' }
    };
    socket.serverSends(validEmittedMessage);

    // Send an invalid message (has structure but invalid type)
    socket.serverSends({ type: 'invalidType', payload: {} });

    expect(msgs.length).toBe(1);
    expect(msgs[0].type).toBe('error');
    if (msgs[0].type === 'error') {
      expect(msgs[0].payload?.message).toBe('test error');
    }
  });

  it('does not reconnect after intentional destroy', async () => {
    const client = createWebSocketClient('ws://test');
    client.connect('A', 'B');
    FakeWebSocket.latest().serverAccepts();

    client.destroy();
    // The socket reports its close on a microtask, as a browser does
    await Promise.resolve();
    vi.advanceTimersByTime(5000);

    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});

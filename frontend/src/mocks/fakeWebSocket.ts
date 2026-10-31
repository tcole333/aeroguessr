type Listener = (event: unknown) => void;

/** A frame the client sent, parsed. */
export interface SentFrame {
  type: string;
  payload?: unknown;
}

/**
 * Just enough of the browser WebSocket for WebSocketClient. A test stubs the global
 * (`vi.stubGlobal('WebSocket', FakeWebSocket)`) and plays the server with serverAccepts,
 * serverSends and serverCloses. As in a browser, close() reports the close asynchronously.
 */
export class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  /** Every socket the client has opened, oldest first. Reset it before each test. */
  static instances: FakeWebSocket[] = [];

  static latest(): FakeWebSocket {
    const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    if (!socket) throw new Error('The client has not opened a WebSocket');
    return socket;
  }

  readyState = FakeWebSocket.CONNECTING;
  sent: SentFrame[] = [];
  private listeners: Record<string, Listener[]> = {};

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  addEventListener(type: string, listener: Listener): void {
    (this.listeners[type] ??= []).push(listener);
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data));
  }

  /** The types of the frames the client sent, leaving out its heartbeat pings. */
  sentTypes(): string[] {
    return this.sent.map((frame) => frame.type).filter((type) => type !== 'ping');
  }

  close(): void {
    if (this.readyState >= FakeWebSocket.CLOSING) return;
    this.readyState = FakeWebSocket.CLOSING;
    queueMicrotask(() => this.serverCloses(1005, ''));
  }

  serverAccepts(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.emit('open', {});
  }

  serverSends(message: unknown): void {
    this.emit('message', { data: JSON.stringify(message) });
  }

  serverCloses(code = 1006, reason = ''): void {
    if (this.readyState === FakeWebSocket.CLOSED) return;
    this.readyState = FakeWebSocket.CLOSED;
    this.emit('close', { code, reason });
  }

  private emit(type: string, event: unknown): void {
    (this.listeners[type] ?? []).forEach((listener) => listener(event));
  }
}

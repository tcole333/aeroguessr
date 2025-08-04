import debug from 'debug';
import { InboundMessage, OutboundMessage, Ping } from '../../types/ws';
import { assertWsMessage } from './validationUtils';

interface Events {
  connected: void;
  disconnected: void;
  message: InboundMessage;
  error: Error;
}

type Listener<K extends keyof Events> = (payload: Events[K]) => void;

class Emitter {
  private listeners: { [K in keyof Events]?: Listener<K>[] } = {} as any;

  on<K extends keyof Events>(event: K, cb: Listener<K>): void {
    this.listeners[event] = this.listeners[event] || [];
    this.listeners[event]!.push(cb as Listener<any>);
  }

  off<K extends keyof Events>(event: K, cb: Listener<K>): void {
    this.listeners[event] = (this.listeners[event] || []).filter((l) => l !== cb) as any;
  }

  emit<K extends keyof Events>(event: K, payload: Events[K]): void {
    (this.listeners[event] || []).forEach((cb) => cb(payload));
  }

  removeAll(): void {
    (Object.keys(this.listeners) as (keyof Events)[]).forEach((key) => {
      this.listeners[key] = [];
    });
  }
}

export interface WebSocketClient {
  connect(roomCode: string, nickname: string, overrideUrl?: string): void;
  send<T extends OutboundMessage>(msg: T): void;
  subscribe(cb: (msg: InboundMessage) => void): () => void;
  on<K extends Exclude<keyof Events, 'message'>>(event: K, cb: Listener<K>): () => void;
  destroy(): void;
}

// Determine WebSocket base URL based on current hostname
const getWsBaseUrl = () => {
  if (typeof window !== 'undefined' && window.location.hostname === 'aeroguessr.com') {
    return 'wss://aeroguessr.com';
  }
  return ((typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_WS_BASE_URL) as string | undefined) ||
    (typeof window !== 'undefined' ? window.location.origin : '');
};

export function createWebSocketClient(
  baseUrl: string = getWsBaseUrl(),
): WebSocketClient {
  let socket: WebSocket | null = null;
  const log = debug('plane:ws');
  const emitter = new Emitter();

  let heartbeat: ReturnType<typeof setInterval> | undefined;
  let missedPongs = 0;
  let reconnectDelay = 500;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  let lastUrl = '';
  const queue: OutboundMessage[] = [];
  let currentRoom = '';
  let currentNickname = '';
  let isIntentionalClose = false;

  function clearTimers() {
    if (heartbeat) clearInterval(heartbeat);
    if (reconnectTimer) clearTimeout(reconnectTimer);
  }

  function flushQueue() {
    while (socket && socket.readyState === WebSocket.OPEN && queue.length) {
      socket.send(JSON.stringify(queue.shift()));
    }
  }

  function scheduleReconnect() {
    clearTimers();
    reconnectTimer = setTimeout(() => {
      connect(currentRoom, currentNickname, lastUrl);
      reconnectDelay = Math.min(reconnectDelay * 2, 4000);
    }, reconnectDelay + Math.floor(Math.random() * 200));
  }

  function handleMessage(data: MessageEvent['data']) {
    try {
      const msg = assertWsMessage(typeof data === 'string' ? data : String(data));
      if (msg) {
        // Debug logging for roundStart messages
        if (msg.type === 'roundStart') {
          console.log('[WS] Received roundStart message from server:', msg);
        }

        if (msg.type === 'pong') {
          missedPongs = 0;
          emitter.emit('message', msg);
          return;
        }

        // Echo back pong when server sends a ping with seq
        if ((msg as any).type === 'ping') {
          const seq = (msg as any).payload?.seq ?? Date.now();
          send({ type: 'pong', payload: { seq } } as any);
          return;
        }

        emitter.emit('message', msg);
      }
    } catch (err) {
      log('invalid message', err);
    }
  }

  function connect(room: string, nickname: string, overrideUrl?: string) {
    currentRoom = room;
    currentNickname = nickname;

    // Allow callers to pass a fully-qualified WebSocket URL returned by the backend. If provided
    // it takes precedence over the constructed URL.
    let url = overrideUrl;
    if (!url) {
      // If baseUrl already includes /api/v0, don't add it again
      const wsBase = baseUrl.replace(/^http/, 'ws');
      url = wsBase.includes('/api/v0')
        ? `${wsBase}/rooms/ws/${room}/${nickname}`
        : `${wsBase}/api/v0/rooms/ws/${room}/${nickname}`;
    }

    // Ensure we use wss:// when on HTTPS
    if (typeof window !== 'undefined' && window.location.protocol === 'https:' && url.startsWith('ws://')) {
      url = url.replace('ws://', 'wss://');
    }

    // If we are already connected (or connecting) to this exact URL, skip.
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) && url === lastUrl) {
      return;
    }
    if (socket) {
      socket.close();
    }
    missedPongs = 0;

    lastUrl = url;

    console.log(`[WS] Connecting to URL: ${url}`);
    socket = new WebSocket(url);
    socket.addEventListener('open', () => {
      console.log(`[WS] Connected to ${url}`);
      emitter.emit('connected', undefined);
      reconnectDelay = 500;
      flushQueue();
    });
    socket.addEventListener('message', (e) => handleMessage(e.data));
    socket.addEventListener('close', (ev) => {
      console.log(`[WS] Disconnected from ${url} (code=${ev.code}, reason=${ev.reason})`);
      emitter.emit('disconnected', undefined);

      // Only reconnect if this wasn't an intentional close
      if (!isIntentionalClose) {
        scheduleReconnect();
      } else {
        // Reset the flag for next connection
        isIntentionalClose = false;
      }
    });
    socket.addEventListener('error', (e) => {
      console.error(`[WS] Error on ${url}:`, e);
      emitter.emit('error', e as any);
    });
    heartbeat = setInterval(() => {
      missedPongs++;
      if (missedPongs > 3) {
        socket?.close();
        scheduleReconnect();
        return;
      }
      // Attach a sequence for backend validation
      send({ type: 'ping', payload: { seq: Date.now() } } as any);
    }, 10000);
  }

  function send<T extends OutboundMessage>(msg: T) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(msg));
    } else {
      queue.push(msg);
      if (queue.length > 100) queue.shift();
    }
  }

  return {
    connect,
    send,
    subscribe(cb) {
      emitter.on('message', cb);
      return () => emitter.off('message', cb);
    },
    on(event, cb) {
      emitter.on(event, cb as any);
      return () => emitter.off(event, cb as any);
    },
    destroy() {
      isIntentionalClose = true;
      clearTimers();
      socket?.close();
      emitter.removeAll();
    },
  };
}

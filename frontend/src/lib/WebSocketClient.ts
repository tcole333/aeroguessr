import debug from 'debug';
import { assertWsMessage, InboundMessage, OutboundMessage, Ping } from '../../types/ws';

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
    this.listeners[event] = (this.listeners[event] || []).filter((l) => l !== cb);
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
  connect(roomCode: string, nickname: string): void;
  send<T extends OutboundMessage>(msg: T): void;
  subscribe(cb: (msg: InboundMessage) => void): () => void;
  destroy(): void;
}

export function createWebSocketClient(baseUrl: string = (import.meta as any).env.VITE_WS_BASE): WebSocketClient {
  let socket: WebSocket | null = null;
  const log = debug('plane:ws');
  const emitter = new Emitter();

  let heartbeat: ReturnType<typeof setInterval> | undefined;
  let missedPongs = 0;
  let reconnectDelay = 500;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  const queue: OutboundMessage[] = [];
  let currentRoom = '';
  let currentNick = '';

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
      connect(currentRoom, currentNick);
      reconnectDelay = Math.min(reconnectDelay * 2, 4000);
    }, reconnectDelay + Math.floor(Math.random() * 200));
  }

  function handleMessage(data: MessageEvent['data']) {
    try {
      const msg = assertWsMessage(JSON.parse(data));
      if ((msg as any).type === 'pong') {
        missedPongs = 0;
      }
      emitter.emit('message', msg);
    } catch (err) {
      log('invalid message', err);
    }
  }

  function connect(room: string, nick: string) {
    currentRoom = room;
    currentNick = nick;
    if (socket) {
      socket.close();
    }
    missedPongs = 0;
    const url = baseUrl.replace(/^http/, 'ws') + `/ws/${room}/${nick}`;
    socket = new WebSocket(url);
    socket.addEventListener('open', () => {
      emitter.emit('connected', undefined);
      reconnectDelay = 500;
      flushQueue();
    });
    socket.addEventListener('message', (e) => handleMessage(e.data));
    socket.addEventListener('close', () => {
      emitter.emit('disconnected', undefined);
      scheduleReconnect();
    });
    socket.addEventListener('error', (e) => {
      emitter.emit('error', e as any);
    });
    heartbeat = setInterval(() => {
      missedPongs++;
      if (missedPongs > 3) {
        socket?.close();
        scheduleReconnect();
        return;
      }
      send({ type: 'ping' } as Ping);
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
    destroy() {
      clearTimers();
      socket?.close();
      emitter.removeAll();
    },
  };
}

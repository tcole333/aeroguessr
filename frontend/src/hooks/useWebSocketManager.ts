import { useEffect } from 'react';
import debug from 'debug';
import { useStore } from './useStore';
import { createWebSocketClient } from '../lib/WebSocketClient';
import type { InboundMessage } from '../../types/ws';

const log = debug('plane:ws:manager');

const client = createWebSocketClient();

function handleInbound(
  msg: InboundMessage,
  updateLatency: (latency: number) => void,
  setLastHeartbeat: (ts: number | null) => void,
): void {
  if (msg.type === 'pong') {
    setLastHeartbeat(Date.now());
    if (msg.payload?.seq) {
      updateLatency(Date.now() - msg.payload.seq);
    }
  }
}

export function useWebSocketManager(
  roomCode: string | null,
  nickname: string | null,
): void {
  const setStatus = useStore((s) => s.connection.setStatus);
  const setError = useStore((s) => s.connection.setError);
  const updateLatency = useStore((s) => s.connection.updateLatency);
  const setLastHeartbeat = useStore((s) => s.connection.setLastHeartbeat);

  useEffect(() => {
    const offMsg = client.subscribe((m) =>
      handleInbound(m, updateLatency, setLastHeartbeat),
    );
    const offConn = client.on('connected', () => setStatus('connected'));
    const offDisc = client.on('disconnected', () => setStatus('reconnecting'));
    const offErr = client.on('error', (e) => {
      log('ws error', e);
      setStatus('error');
      setError((e as Error).message);
    });
    return () => {
      offMsg();
      offConn();
      offDisc();
      offErr();
    };
  }, [setStatus, setError, updateLatency, setLastHeartbeat]);

  useEffect(() => {
    if (roomCode && nickname) {
      setStatus('connecting');
      client.connect(roomCode, nickname);
    }
  }, [roomCode, nickname, setStatus]);
}

export { client as webSocketClient };

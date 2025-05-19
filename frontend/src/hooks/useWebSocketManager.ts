import { useEffect } from 'react';
import debug from 'debug';
import { useStore } from './useStore';
import { createWebSocketClient } from '../lib/WebSocketClient';
import type { InboundMessage } from '../../types/ws';

const log = debug('plane:ws:manager');

const client = createWebSocketClient();

interface SliceActions {
  hydrate: (state: any) => void;
  applyDelta: (delta: any) => void;
  setRoundStart: (p: any) => void;
  setRoundResult: (p: any) => void;
  upsertPlanes: (p: any[]) => void;
  removePlanes: (ids: string[]) => void;
}

function handleInbound(
  msg: InboundMessage,
  updateLatency: (latency: number) => void,
  setLastHeartbeat: (ts: number | null) => void,
  actions: SliceActions,
): void {
  if (msg.type === 'pong') {
    setLastHeartbeat(Date.now());
    if (msg.payload?.seq) {
      updateLatency(Date.now() - msg.payload.seq);
    }
    return;
  }

  switch (msg.type) {
    case 'stateSync':
      actions.hydrate(msg.payload);
      break;
    case 'delta':
      if (msg.payload.planes?.updated) {
        actions.upsertPlanes(msg.payload.planes.updated);
      }
      if (msg.payload.planes?.removed) {
        actions.removePlanes(msg.payload.planes.removed);
      }
      actions.applyDelta(msg.payload);
      break;
    case 'roundStart':
      actions.setRoundStart(msg.payload);
      break;
    case 'roundResult':
      actions.setRoundResult(msg.payload);
      break;
    default:
      // no-op for unhandled types
      break;
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
  const hydrate = useStore((s) => s.game.hydrate);
  const applyDelta = useStore((s) => s.game.applyDelta);
  const setRoundStart = useStore((s) => s.game.setRoundStart);
  const setRoundResult = useStore((s) => s.game.setRoundResult);
  const upsertPlanes = useStore((s) => s.planes.upsertPlanes);
  const removePlanes = useStore((s) => s.planes.removePlanes);

  useEffect(() => {
    const actions = {
      hydrate,
      applyDelta,
      setRoundStart,
      setRoundResult,
      upsertPlanes,
      removePlanes,
    };
    const offMsg = client.subscribe((m) =>
      handleInbound(m, updateLatency, setLastHeartbeat, actions),
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
  }, [
    setStatus,
    setError,
    updateLatency,
    setLastHeartbeat,
    hydrate,
    applyDelta,
    setRoundStart,
    setRoundResult,
    upsertPlanes,
    removePlanes,
  ]);

  useEffect(() => {
    if (roomCode && nickname) {
      setStatus('connecting');
      client.connect(roomCode, nickname);
    }
  }, [roomCode, nickname, setStatus]);
}

export { client as webSocketClient };

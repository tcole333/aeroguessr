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
  setSelectedPlane: (hex: string | null) => void;
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
      if (msg.payload) {
        const { planes } = msg.payload as any;
        if (planes?.updated) {
          actions.upsertPlanes(planes.updated);
        }
        if (planes?.removed) {
          actions.removePlanes(planes.removed);
        }
        actions.applyDelta(msg.payload);
      }
      break;
    case 'roundStart':
      actions.setRoundStart(msg.payload);
      actions.setSelectedPlane(null);
      break;
    case 'roundResult':
      actions.setRoundResult(msg.payload);
      break;
    case 'planeSelectedConfirm':
      actions.setSelectedPlane(null);
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
  const setSelectedPlane = useStore((s) => s.game.setSelectedPlane);
  const upsertPlanes = useStore((s) => s.planes.upsertPlanes);
  const removePlanes = useStore((s) => s.planes.removePlanes);
  const wsUrl = useStore((s) => s.connection.wsUrl);

  useEffect(() => {
  const actions = {
    hydrate,
    applyDelta,
    setRoundStart,
    setRoundResult,
    setSelectedPlane,
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
    setSelectedPlane,
    upsertPlanes,
    removePlanes,
  ]);

  useEffect(() => {
    if (roomCode && nickname) {
      setStatus('connecting');
      client.connect(roomCode, nickname, wsUrl ?? undefined);
    }
  }, [roomCode, nickname, wsUrl, setStatus]);
}

export { client as webSocketClient };

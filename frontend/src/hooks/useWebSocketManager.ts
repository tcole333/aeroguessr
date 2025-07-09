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
  setGuessDirection: (direction: string | null) => void;
  setHostNickname: (nick: string | null) => void;
  upsertPlanes: (p: any[]) => void;
  removePlanes: (ids: string[]) => void;
  setExpandedPlane: (hex: string | null) => void;
  setActivePanel: (panel: 'planes' | 'leaderboard' | 'settings') => void;
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
        // Only log if delta contains round data
        if ((msg.payload as any).round) {
          console.log('[WS] Received delta message with round data:', msg.payload);
        }
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
      try {
        actions.setRoundStart(msg.payload);
        // Ensure the active round plane is expanded in the UI
        actions.setExpandedPlane(msg.payload.hex);
      } catch (error) {
        console.error('[WS] Error handling roundStart:', error);
      }
      break;
    case 'roundResult':
      actions.setRoundResult(msg.payload);
      break;
    case 'newHost':
      actions.setHostNickname(msg.payload.nickname);
      break;
    case 'planeSelectedConfirm':
      if (msg.payload?.hex) {
        actions.setSelectedPlane(msg.payload.hex);
        if (msg.payload.guess_direction) {
          actions.setGuessDirection(msg.payload.guess_direction);
        }
      }
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
  const setGuessDirection = useStore((s) => s.game.setGuessDirection);
  const setHostNickname = useStore((s) => s.game.setHostNickname);
  const upsertPlanes = useStore((s) => s.planes.upsertPlanes);
  const removePlanes = useStore((s) => s.planes.removePlanes);
  const wsUrl = useStore((s) => s.connection.wsUrl);
  const setExpandedPlane = useStore((s) => s.ui.setExpandedPlane);
  const setActivePanel = useStore((s) => s.ui.setActivePanel);
  const isRejoinAttempt = useStore((s) => s.connection.isRejoinAttempt);
  const setIsRejoinAttempt = useStore((s) => s.connection.setIsRejoinAttempt);
  const clearConnectionDetails = useStore((s) => s.connection.clearConnectionDetails);
  const setCurrentView = useStore((s) => s.ui.setCurrentView);

  useEffect(() => {
  const actions = {
    hydrate,
    applyDelta,
    setRoundStart,
    setRoundResult,
    setSelectedPlane,
    setGuessDirection,
    setHostNickname,
    upsertPlanes,
    removePlanes,
    setExpandedPlane,
    setActivePanel,
  };
    const offMsg = client.subscribe((m) =>
      handleInbound(m, updateLatency, setLastHeartbeat, actions),
    );
    const offConn = client.on('connected', () => {
      setStatus('connected');
      // Clear rejoin attempt flag on successful connection
      if (isRejoinAttempt) {
        setIsRejoinAttempt(false);
        console.log('[WebSocket] Successfully rejoined room');
      }
    });
    const offDisc = client.on('disconnected', () => setStatus('reconnecting'));
    const offErr = client.on('error', (e) => {
      log('ws error', e);
      setStatus('error');
      setError((e as Error).message);

      // Handle rejoin failures
      if (isRejoinAttempt) {
        console.log('[WebSocket] Rejoin failed, redirecting to home');
        setIsRejoinAttempt(false);
        clearConnectionDetails();
        setCurrentView('home');
        setError('Unable to rejoin previous session. Please join again.');
      }
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
    setGuessDirection,
    setHostNickname,
    upsertPlanes,
    removePlanes,
    setExpandedPlane,
    setActivePanel,
    isRejoinAttempt,
    setIsRejoinAttempt,
    clearConnectionDetails,
    setCurrentView,
  ]);

  useEffect(() => {
    if (roomCode && nickname) {
      setStatus('connecting');
      client.connect(roomCode, nickname, wsUrl ?? undefined);
    }
  }, [roomCode, nickname, wsUrl, setStatus]);
}

export { client as webSocketClient };

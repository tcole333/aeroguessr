import { useEffect } from 'react';
import debug from 'debug';
import { toast } from 'sonner';
import { useStore } from './useStore';
import { createWebSocketClient } from '../lib/WebSocketClient';
import type { ErrorPayload, InboundMessage } from '../../types/ws';

const log = debug('plane:ws:manager');

const client = createWebSocketClient();

const FALLBACK_ERROR_MESSAGE = 'Something went wrong. Please try again.';

/**
 * Shows a server rejection, so a refused action no longer fails silently. The server
 * records no guess it refuses for an unknown airport, so the guess forms show that one
 * inline and let the player send another; every other rejection is a toast. The text
 * comes from the server, which keeps answer airports out of every message before
 * roundResult.
 */
function showServerError(
  payload: ErrorPayload | undefined,
  setGuessRejection: (message: string) => void,
): void {
  const message = payload?.message || FALLBACK_ERROR_MESSAGE;
  log('server error', payload?.code, message);
  if (payload?.code === 'UNKNOWN_AIRPORT_CODE') {
    setGuessRejection(message);
    return;
  }
  // One id per error folds repeats (e.g. a double click) into a single toast
  toast.error(message, { id: `${payload?.code ?? 'error'}:${message}` });
}

interface SliceActions {
  hydrate: (state: any) => void;
  applyDelta: (delta: any) => void;
  setRoundStart: (p: any) => void;
  setRoundResult: (p: any) => void;
  setSelectedPlane: (hex: string | null) => void;
  setHostNickname: (nick: string | null) => void;
  setGuessRejection: (message: string | null) => void;
  addPlayer: (nickname: string) => void;
  removePlayer: (nickname: string) => void;
  upsertPlanes: (p: any[]) => void;
  removePlanes: (ids: string[]) => void;
  setExpandedPlane: (hex: string | null) => void;
}

function handleInbound(msg: InboundMessage, actions: SliceActions): void {
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
        if (planes?.removed && planes.removed.length > 0) {
          actions.removePlanes(planes.removed);
        }
        actions.applyDelta(msg.payload);
      }
      break;
    case 'roundStart':
      try {
        if (msg.payload) {
          actions.setRoundStart(msg.payload);
          // Ensure the active round plane is expanded in the UI
          actions.setExpandedPlane(msg.payload.hex);
        }
      } catch (error) {
        console.error('[WS] Error handling roundStart:', error);
      }
      break;
    case 'roundResult':
      actions.setRoundResult(msg.payload);
      break;
    case 'playerJoined':
      if (msg.payload?.nickname) {
        actions.addPlayer(msg.payload.nickname);
      }
      break;
    case 'playerLeft':
      if (msg.payload?.nickname) {
        actions.removePlayer(msg.payload.nickname);
      }
      break;
    case 'newHost':
      if (msg.payload?.nickname) {
        actions.setHostNickname(msg.payload.nickname);
      }
      break;
    case 'planeSelectedConfirm':
      if (msg.payload?.hex) {
        actions.setSelectedPlane(msg.payload.hex);
      }
      break;
    case 'error':
      showServerError(msg.payload, actions.setGuessRejection);
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
  const hydrate = useStore((s) => s.game.hydrate);
  const applyDelta = useStore((s) => s.game.applyDelta);
  const setRoundStart = useStore((s) => s.game.setRoundStart);
  const setRoundResult = useStore((s) => s.game.setRoundResult);
  const setSelectedPlane = useStore((s) => s.game.setSelectedPlane);
  const setHostNickname = useStore((s) => s.game.setHostNickname);
  const setGuessRejection = useStore((s) => s.game.setGuessRejection);
  const addPlayer = useStore((s) => s.game.addPlayer);
  const removePlayer = useStore((s) => s.game.removePlayer);
  const upsertPlanes = useStore((s) => s.planes.upsertPlanes);
  const removePlanes = useStore((s) => s.planes.removePlanes);
  const clearPlanes = useStore((s) => s.planes.clear);
  const wsUrl = useStore((s) => s.connection.wsUrl);
  const setExpandedPlane = useStore((s) => s.ui.setExpandedPlane);
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
    setHostNickname,
    setGuessRejection,
    addPlayer,
    removePlayer,
    upsertPlanes,
    removePlanes,
    setExpandedPlane,
  };
    const offMsg = client.subscribe((m) => handleInbound(m, actions));
    const offConn = client.on('connected', () => {
      setStatus('connected');
      // Clear rejoin attempt flag on successful connection
      if (isRejoinAttempt) {
        setIsRejoinAttempt(false);
        log('rejoined room');
      }
    });
    const offDisc = client.on('disconnected', () => setStatus('reconnecting'));
    const offErr = client.on('error', (e) => {
      log('ws error', e);
      setStatus('error');
      setError((e as Error).message);

      // Handle rejoin failures
      if (isRejoinAttempt) {
        log('rejoin failed; back to home');
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
    hydrate,
    applyDelta,
    setRoundStart,
    setRoundResult,
    setSelectedPlane,
    setHostNickname,
    setGuessRejection,
    addPlayer,
    removePlayer,
    upsertPlanes,
    removePlanes,
    setExpandedPlane,
    isRejoinAttempt,
    setIsRejoinAttempt,
    clearConnectionDetails,
    setCurrentView,
  ]);

  useEffect(() => {
    if (roomCode && nickname) {
      setStatus('connecting');
      // Clear planes when connecting to a new room to prevent accumulation
      clearPlanes();
      client.connect(roomCode, nickname, wsUrl ?? undefined);
    }
  }, [roomCode, nickname, wsUrl, setStatus, clearPlanes]);
}

export { client as webSocketClient };

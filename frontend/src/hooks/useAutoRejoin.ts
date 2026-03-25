import { useEffect, useRef } from 'react';
import debug from 'debug';
import { useStore } from './useStore';

const log = debug('plane:auto-rejoin');

/**
 * Custom hook that handles automatic rejoin logic on app startup.
 * If there's persisted connection data (roomCode, wsUrl, nickname) and the current view is 'game',
 * it automatically attempts to rejoin the previous session.
 */
export function useAutoRejoin(): void {
  const hasRun = useRef(false);
  const roomCode = useStore((s) => s.connection.roomCode);
  const wsUrl = useStore((s) => s.connection.wsUrl);
  const nickname = useStore((s) => s.connection.nickname);
  const currentView = useStore((s) => s.ui.currentView);
  const setIsRejoinAttempt = useStore((s) => s.connection.setIsRejoinAttempt);
  const clearConnectionDetails = useStore((s) => s.connection.clearConnectionDetails);

  useEffect(() => {
    // Only run once on app startup
    if (hasRun.current) return;
    hasRun.current = true;

    // Check if we have persisted connection data
    const hasConnectionData = roomCode && wsUrl && nickname;
    const shouldRejoin = hasConnectionData && currentView === 'game';

    if (shouldRejoin) {
      log('attempting rejoin room=%s nickname=%s', roomCode, nickname);

      // Set the rejoin flag so other components know this is an automatic rejoin
      setIsRejoinAttempt(true);

      // The WebSocket manager will automatically connect based on the persisted data
      // We don't need to do anything else here - the connection will be established
      // and if it fails, the error handling will be managed by the WebSocket manager
    } else if (hasConnectionData && currentView === 'home') {
      // If we have connection data but we're on the home page, clear it
      // This can happen if the user manually navigated away
      log('clearing stale connection data');
      clearConnectionDetails();
    }
  }, [
    roomCode,
    wsUrl,
    nickname,
    currentView,
    setIsRejoinAttempt,
    clearConnectionDetails,
  ]);
}

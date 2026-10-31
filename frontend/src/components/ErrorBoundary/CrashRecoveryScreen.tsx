import { useState } from 'react';
import { useStore } from '../../hooks/useStore';
import { selectDarkMode, selectCurrentView } from '../../features/ui/selectors';
import { selectNickname, selectRoomCode, selectWsUrl } from '../../features/connection/selectors';

interface CrashRecoveryScreenProps {
  error: Error;
  onReload?: () => void;
}

type Recovery = { kind: 'rejoin'; roomCode: string } | { kind: 'solo' } | { kind: 'reload' };

const reloadPage = (): void => window.location.reload();

const MESSAGES: Record<Recovery['kind'], string> = {
  rejoin: 'Rejoin to pick up where you left off, or go back to the home screen.',
  solo: "Solo games can't be resumed, so head back to the home screen to start a new one.",
  reload: 'Reload the page to try again, or go back to the home screen.',
};

function useRecovery(): Recovery {
  const roomCode = useStore(selectRoomCode);
  const wsUrl = useStore(selectWsUrl);
  const nickname = useStore(selectNickname);
  const currentView = useStore(selectCurrentView);

  // Decided once, from the session at the time of the crash: "Back to home"
  // clears the session just before the page reloads, and the screen should not
  // change under the player while it does.
  const [recovery] = useState((): Recovery => {
    // The backend deletes a solo room as soon as its socket closes, so a reload
    // can only fail to rejoin it.
    if (roomCode?.startsWith('solo:')) return { kind: 'solo' };
    // Same condition useAutoRejoin checks after the reload.
    if (roomCode && wsUrl && nickname && currentView === 'game') return { kind: 'rejoin', roomCode };
    return { kind: 'reload' };
  });
  return recovery;
}

const PRIMARY_BUTTON = 'w-full px-4 py-2 rounded bg-blue-600 hover:bg-blue-700 text-white font-medium';
const SECONDARY_BUTTON =
  'w-full px-4 py-2 rounded border border-gray-300 dark:border-gray-600 text-gray-800 dark:text-gray-100 hover:bg-gray-50 dark:hover:bg-gray-700';

/**
 * Shown by AppErrorBoundary in place of the app after a render crash. Every
 * action reloads the page, which drops the in-memory state that crashed.
 *
 * "Rejoin" keeps the persisted session, so useAutoRejoin puts the player back
 * in their multiplayer room. "Back to home" clears the session first, and is
 * the only way out of a solo game.
 */
export function CrashRecoveryScreen({ error, onReload = reloadPage }: CrashRecoveryScreenProps): JSX.Element {
  const recovery = useRecovery();
  const darkMode = useStore(selectDarkMode);
  const clearRoom = useStore((s) => s.game.leaveRoom);

  const handleBackToHome = () => {
    // Reload instead of re-rendering in place: the WebSocket client may still
    // hold queued messages or a pending reconnect from before the crash, and a
    // reload is the only reset for it. Unloading closes the socket, which the
    // server treats as leaving the room. The store persists synchronously, so
    // the new page starts on the home screen.
    clearRoom();
    onReload();
  };

  return (
    <div className={darkMode ? 'dark' : undefined}>
      <div className="min-h-screen flex items-center justify-center p-4 bg-gray-100 dark:bg-gray-900">
        <div className="w-full max-w-md p-6 space-y-4 rounded-lg shadow bg-white dark:bg-gray-800">
          <div role="alert" className="space-y-2">
            <h1 className="text-xl font-bold text-gray-900 dark:text-white">Something went wrong</h1>
            <p className="text-sm text-gray-600 dark:text-gray-300">
              The game hit an unexpected error. {MESSAGES[recovery.kind]}
            </p>
          </div>

          <div className="space-y-2">
            {recovery.kind !== 'solo' && (
              <button type="button" autoFocus onClick={() => onReload()} className={PRIMARY_BUTTON}>
                {recovery.kind === 'rejoin' ? `Rejoin room ${recovery.roomCode}` : 'Reload'}
              </button>
            )}
            <button
              type="button"
              autoFocus={recovery.kind === 'solo'}
              onClick={handleBackToHome}
              className={recovery.kind === 'solo' ? PRIMARY_BUTTON : SECONDARY_BUTTON}
            >
              Back to home
            </button>
          </div>

          <details className="text-xs text-gray-500 dark:text-gray-400">
            <summary className="cursor-pointer">Error details</summary>
            <pre className="mt-2 whitespace-pre-wrap break-words">{error.message}</pre>
          </details>
        </div>
      </div>
    </div>
  );
}

import { useCallback } from 'react';
import { Toaster } from 'sonner';
import MapView from '../../features/map/components/MapView';
import SlidingPanel from './SlidingPanel';
import { useStore } from '../../hooks/useStore';
import { selectDarkMode, selectRetroMode } from '../../features/ui/selectors';
import { useWebSocketManager } from '../../hooks/useWebSocketManager';
import { selectRoomCode, selectPlayerNickname } from '../../features/connection/selectors';
import { RoundResultModal } from '../ui/RoundResultModal';
import GuessForm from '../../features/game/components/GuessForm';

export default function AppShell(): JSX.Element {
  const darkMode = useStore(selectDarkMode);
  const retroMode = useStore(selectRetroMode);
  const setExpandedPlane = useStore((s) => s.ui.setExpandedPlane);

  // Wire up WebSocket connection whenever room/nickname are present
  const roomCode = useStore(selectRoomCode);
  const playerNickname = useStore(selectPlayerNickname);
  useWebSocketManager(roomCode, playerNickname);

  const handlePlaneClick = useCallback((hex: string) => {
    setExpandedPlane(hex);
  }, [setExpandedPlane]);

  // Build theme classes
  const themeClasses = [
    darkMode ? 'dark' : '',
    retroMode ? 'retro' : '',
  ].filter(Boolean).join(' ');

  return (
    <>
      <div className={`h-screen w-screen flex flex-col md:flex-row overflow-x-hidden ${retroMode ? 'bg-retro-bg' : 'bg-gray-100 dark:bg-gray-900'} ${themeClasses}`}>
        {/* Map container: flex-1 so it fills remaining space */}
        <div className="flex-1 h-1/2 w-full md:h-full">
          <MapView onPlaneClick={handlePlaneClick} />
        </div>
        {/* Panel container: takes bottom half on mobile, fixed width on desktop */}
        <SlidingPanel />
        {/* Modal for round results */}
        <RoundResultModal />
        {/* Guess form modal */}
        <GuessForm />
      </div>
      {/* Toasts for server errors, e.g. a refused round action */}
      <Toaster position="top-center" theme={darkMode ? 'dark' : 'light'} richColors />
    </>
  );
}

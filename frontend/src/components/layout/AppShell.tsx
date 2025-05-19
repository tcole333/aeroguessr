import MapView from '../../features/map/components/MapView';
import SlidingPanel from './SlidingPanel';
import { useStore } from '../../hooks/useStore';
import { selectDarkMode } from '../../features/ui/selectors';
import { useWebSocketManager } from '../../hooks/useWebSocketManager';
import { selectRoomCode, selectPlayerNickname } from '../../features/connection/selectors';

export default function AppShell(): JSX.Element {
  const darkMode = useStore(selectDarkMode);

  // Wire up WebSocket connection whenever room/nickname are present
  const roomCode = useStore(selectRoomCode);
  const playerNickname = useStore(selectPlayerNickname);
  useWebSocketManager(roomCode, playerNickname);

  return (
    <div className={`h-screen w-screen flex flex-col md:flex-row bg-gray-100 dark:bg-gray-900 ${darkMode ? 'dark' : ''}`}>
      {/* Map container: flex-1 so it fills remaining space */}
      <div className="flex-1 h-1/2 w-full md:h-full">
        <MapView />
      </div>
      {/* Panel container: takes bottom half on mobile, fixed width on desktop */}
      <SlidingPanel />
    </div>
  );
}

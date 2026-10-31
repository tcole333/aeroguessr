import { useStore } from '../../../hooks/useStore';
import { selectDarkMode, selectRetroMode } from '../../ui/selectors';
import { selectServerVersion } from '../../config/selectors';
import { webSocketClient } from '../../../hooks/useWebSocketManager';

export default function SettingsPanelContent(): JSX.Element {
  const darkMode = useStore(selectDarkMode);
  const retroMode = useStore(selectRetroMode);
  // For bug reports: the version this install runs, from the client config
  const version = useStore(selectServerVersion);
  const toggleDarkMode = useStore((s) => s.ui.toggleDarkMode);
  const toggleRetroMode = useStore((s) => s.ui.toggleRetroMode);
  const leaveRoom = useStore((s) => s.game.leaveRoom);
  const clearConnectionDetails = useStore((s) => s.connection.clearConnectionDetails);
  const setCurrentView = useStore((s) => s.ui.setCurrentView);

  const handleLeave = () => {
    // Send leave message to server
    webSocketClient.send({ type: 'leave', payload: {} });

    // Clear game and connection state
    leaveRoom();
    clearConnectionDetails();

    // Return to home view
    setCurrentView('home');

    // Clean up WebSocket connection
    webSocketClient.destroy();

    // Force clear persisted storage to prevent auto-rejoin
    // This ensures the localStorage is cleared immediately
    localStorage.removeItem('plane-session');
  };

  // Retro-themed settings panel
  if (retroMode) {
    return (
      <div className="space-y-6">
        {/* Chart Theme Toggle */}
        <label
          htmlFor="retroModeToggle"
          className="flex items-center justify-between cursor-pointer"
        >
          <div>
            <span className="font-display text-sm uppercase tracking-widest text-retro-text">
              Chart Mode
            </span>
            <p className="text-xs font-display text-retro-text-muted mt-1">
              Vintage aviation chart aesthetic
            </p>
          </div>
          <div className="relative">
            <input
              id="retroModeToggle"
              type="checkbox"
              className="sr-only peer"
              checked={retroMode}
              onChange={toggleRetroMode}
            />
            <div className="w-12 h-6 bg-retro-panel border border-retro-border peer-checked:border-retro-primary transition-colors"></div>
            <div className="absolute left-1 top-1 w-4 h-4 bg-retro-border peer-checked:bg-retro-primary peer-checked:translate-x-6 transition-all"></div>
          </div>
        </label>

        {/* Night Mode Toggle */}
        <label
          htmlFor="nightModeToggle"
          className="flex items-center justify-between cursor-pointer"
        >
          <span className="font-display text-sm uppercase tracking-widest text-retro-text">
            Night Mode
          </span>
          <div className="relative">
            <input
              id="nightModeToggle"
              type="checkbox"
              className="sr-only peer"
              checked={darkMode}
              onChange={toggleDarkMode}
            />
            <div className="w-12 h-6 bg-retro-panel border border-retro-border peer-checked:border-retro-primary transition-colors"></div>
            <div className="absolute left-1 top-1 w-4 h-4 bg-retro-border peer-checked:bg-retro-primary peer-checked:translate-x-6 transition-all"></div>
          </div>
        </label>

        {/* Leave Room Button */}
        <button
          type="button"
          onClick={handleLeave}
          className="w-full py-3 px-3 font-display uppercase tracking-widest text-sm border border-retro-accent bg-transparent text-retro-accent hover:bg-retro-accent hover:text-retro-panel transition-all"
        >
          Leave Gate
        </button>

        {version && (
          <p className="text-center font-display text-xs tracking-wider text-retro-text-muted">
            AeroGuessr {version}
          </p>
        )}
      </div>
    );
  }

  // Original settings panel
  return (
    <div className="space-y-6 p-1">
      {/* Chart Theme Toggle - always visible */}
      <label
        htmlFor="retroModeToggle"
        className="flex items-center justify-between cursor-pointer"
      >
        <div>
          <span className="text-gray-700 dark:text-gray-300">Chart Mode</span>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            Vintage aviation chart aesthetic
          </p>
        </div>
        <div className="relative">
          <input
            id="retroModeToggle"
            type="checkbox"
            className="sr-only peer"
            checked={retroMode}
            onChange={toggleRetroMode}
          />
          <div className="w-10 h-6 bg-gray-300 rounded-full peer-checked:bg-amber-500 dark:bg-gray-600 peer-checked:dark:bg-amber-600 transition-colors"></div>
          <div className="absolute left-1 top-1 w-4 h-4 bg-white rounded-full peer-checked:translate-x-full transition-transform"></div>
        </div>
      </label>

      {/* Night Mode Toggle */}
      <label
        htmlFor="nightModeToggle"
        className="flex items-center justify-between cursor-pointer"
      >
        <span className="text-gray-700 dark:text-gray-300">Night Mode</span>
        <div className="relative">
          <input
            id="nightModeToggle"
            type="checkbox"
            className="sr-only peer"
            checked={darkMode}
            onChange={toggleDarkMode}
          />
          <div className="w-10 h-6 bg-gray-300 rounded-full peer-checked:bg-primary-600 dark:bg-gray-600 peer-checked:dark:bg-primary-500 transition-colors"></div>
          <div className="absolute left-1 top-1 w-4 h-4 bg-white rounded-full peer-checked:translate-x-full transition-transform"></div>
        </div>
      </label>

      <button
        type="button"
        onClick={handleLeave}
        className="w-full rounded bg-red-600 hover:bg-red-700 px-3 py-2 text-white font-semibold transition-colors"
      >
        Leave Room
      </button>

      {version && (
        <p className="text-center text-xs text-gray-500 dark:text-gray-400">AeroGuessr {version}</p>
      )}
    </div>
  );
}

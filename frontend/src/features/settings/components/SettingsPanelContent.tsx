import { useStore } from '../../../hooks/useStore';
import { selectDarkMode } from '../../ui/selectors';
import { selectIsSolo } from '../../game/selectors';
import { selectPlayerNickname } from '../../connection/selectors';

export default function SettingsPanelContent(): JSX.Element {
  const darkMode = useStore(selectDarkMode);
  const toggleDarkMode = useStore((s) => s.ui.toggleDarkMode);
  const isSolo = useStore(selectIsSolo);

  const handleLeave = () => {
    // eslint-disable-next-line no-console
    console.log(isSolo ? 'Leaving solo mode' : 'Attempting to leave room');
  };

  return (
    <div className="space-y-6 p-1"> {/* Added p-1 for slight spacing if toggle is near edge, adjust as needed */}
      <label
        htmlFor="nightModeToggle"
        className="flex items-center justify-between cursor-pointer"
      >
        <span className="text-gray-700 dark:text-gray-300">Night Mode</span>
        <div className="relative">
          <input
            id="nightModeToggle"
            type="checkbox"
            className="sr-only peer" // Hide default checkbox, make it a peer
            checked={darkMode}
            onChange={toggleDarkMode}
          />
          {/* Toggle background */}
          <div className="w-10 h-6 bg-gray-300 rounded-full peer-checked:bg-primary-600 dark:bg-gray-600 peer-checked:dark:bg-primary-500 transition-colors"></div>
          {/* Toggle knob */}
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
    </div>
  );
}

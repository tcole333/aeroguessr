import { useStore } from '../../../hooks/useStore';
import { selectDarkMode } from '../../ui/selectors';
import { selectHost, selectIsSolo } from '../../game/selectors';

export default function SettingsPanelContent(): JSX.Element {
  const darkMode = useStore(selectDarkMode);
  const toggleDarkMode = useStore((s) => s.ui.toggleDarkMode);
  const hostNickname = useStore(selectHost);
  const isSolo = useStore(selectIsSolo);
  const myNickname = useStore(
    (s) => (s.connection as unknown as { nickname?: string }).nickname,
  );

  const handleLeave = () => {
    // eslint-disable-next-line no-console
    console.log(isSolo ? 'Leaving solo mode' : 'Attempting to leave room');
  };

  const isHost = !isSolo && hostNickname && myNickname === hostNickname;

  return (
    <div className="space-y-4">
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={darkMode} onChange={toggleDarkMode} />
        <span>Night Mode</span>
      </label>
      <button
        type="button"
        onClick={handleLeave}
        className="rounded bg-red-500 px-3 py-2 text-white"
      >
        Leave Room
      </button>
      {isHost && (
        <div>
          <h3 className="font-bold">Host Controls</h3>
          <p className="text-sm text-gray-500">Coming soon…</p>
        </div>
      )}
    </div>
  );
}

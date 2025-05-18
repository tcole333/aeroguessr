import { useStore } from '../../hooks/useStore';
import { selectActivePanel } from '../../features/ui/selectors';
import type { Panel } from '../../features/ui/uiSlice';

const tabs: Panel[] = ['planes', 'leaderboard', 'settings'];

export default function PanelTabs(): JSX.Element {
  const active = useStore(selectActivePanel);
  const setActive = useStore((s) => s.ui.setActivePanel);

  return (
    <div role="tablist" className="flex border-b border-gray-700">
      {tabs.map((tab) => (
        <button
          key={tab}
          role="tab"
          aria-selected={active === tab}
          onClick={() => setActive(tab)}
          className={`flex-1 py-2 text-center capitalize ${
            active === tab ? 'font-bold border-b-2 border-primary-500' : ''
          }`}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}

import { useStore } from '../../hooks/useStore';
import { selectActivePanel, selectRetroMode } from '../../features/ui/selectors';
import type { Panel } from '../../features/ui/uiSlice';

const tabs: Panel[] = ['planes', 'leaderboard', 'settings'];

// Retro tab labels - airport terminal style
const retroLabels: Record<Panel, string> = {
  planes: 'DEPARTURES',
  leaderboard: 'STANDINGS',
  settings: 'TERMINAL',
};

export default function PanelTabs({
  className = '',
}: { className?: string }): JSX.Element {
  const active = useStore(selectActivePanel);
  const retroMode = useStore(selectRetroMode);
  const setActivePanel = useStore((s) => s.ui.setActivePanel);

  if (retroMode) {
    return (
      <div
        role="tablist"
        className={`flex border-b-2 border-retro-border bg-retro-panel ${className}`}
      >
        {tabs.map((tab) => {
          const isActive = active === tab;
          return (
            <button
              key={tab}
              role="tab"
              aria-selected={isActive}
              onClick={() => setActivePanel(tab)}
              className={`flex-1 py-3 text-center font-display text-xs uppercase tracking-[0.18em] transition-all ${
                isActive
                  ? 'bg-retro-panel text-retro-primary border-b-2 border-retro-primary font-semibold'
                  : 'text-retro-sage hover:text-retro-text'
              }`}
            >
              {retroLabels[tab]}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div role="tablist" className={`flex border-b border-gray-700 ${className}`}>
      {tabs.map((tab) => (
        <button
          key={tab}
          role="tab"
          aria-selected={active === tab}
          onClick={() => setActivePanel(tab)}
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

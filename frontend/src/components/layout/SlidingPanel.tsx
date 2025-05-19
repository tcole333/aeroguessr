import PanelTabs from './PanelTabs';
import PlaneListPanelContent from '../../features/planes/components/PlaneListPanelContent';
import LeaderboardPanelContent from '../../features/leaderboard/components/LeaderboardPanelContent';
import SettingsPanelContent from '../../features/settings/components/SettingsPanelContent';
import { useStore } from '../../hooks/useStore';
import { selectActivePanel } from '../../features/ui/selectors';

export default function SlidingPanel(): JSX.Element {
  const activePanel = useStore(selectActivePanel);

  let content: JSX.Element;
  switch (activePanel) {
    case 'leaderboard':
      content = <LeaderboardPanelContent />;
      break;
    case 'settings':
      content = <SettingsPanelContent />;
      break;
    default:
      content = <PlaneListPanelContent />;
  }

  return (
    <div
      // Mobile: flex item, takes bottom half. Desktop: specific width, full height.
      className="flex flex-col h-1/2 w-full bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 md:w-96 md:h-full"
    >
      <PanelTabs />
      <div className="flex-1 overflow-y-auto p-4">{content}</div>
    </div>
  );
}

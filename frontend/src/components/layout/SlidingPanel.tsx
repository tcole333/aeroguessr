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
      className="bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 fixed bottom-0 left-0 right-0 h-1/2 md:relative md:h-full md:w-96 md:flex md:flex-col z-10"
    >
      <PanelTabs />
      <div className="flex-1 overflow-y-auto p-4">{content}</div>
    </div>
  );
}

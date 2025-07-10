import PanelTabs from './PanelTabs';
import PlaneListPanelContent from '../../features/planes/components/PlaneListPanelContent';
import LeaderboardPanelContent from '../../features/leaderboard/components/LeaderboardPanelContent';
import SettingsPanelContent from '../../features/settings/components/SettingsPanelContent';
import { RoomCodeDisplay } from '../ui/RoomCodeDisplay';
import { ScoreModeIndicator } from '../ui/ScoreModeIndicator';
import { GameStatusIndicator } from '../ui/GameStatusIndicator';
import { useStore } from '../../hooks/useStore';
import {
  selectActivePanel,
  selectIsPanelOpen,
} from '../../features/ui/selectors';
import chevronUpUrl from '../../assets/icons/chevron-up.svg';
import chevronDownUrl from '../../assets/icons/chevron-down.svg';

export default function SlidingPanel(): JSX.Element {
  const activePanel = useStore(selectActivePanel);
  const isPanelOpen = useStore(selectIsPanelOpen);
  const togglePanelOpen = useStore((s) => s.ui.togglePanelOpen);

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
      className={`flex flex-col w-full bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 transition-all duration-300 ease-in-out ${isPanelOpen ? 'h-1/2 md:w-96' : 'h-16 overflow-hidden md:w-16 md:overflow-hidden'} md:h-full`}
    >
      <div className="border-b border-gray-700">
        <div className="flex items-center justify-between p-2">
          <RoomCodeDisplay className={isPanelOpen ? '' : 'hidden md:hidden'} />
          <button
            type="button"
            onClick={togglePanelOpen}
            aria-label={isPanelOpen ? 'Minimize panel' : 'Maximize panel'}
            aria-expanded={isPanelOpen}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
          >
            <img src={isPanelOpen ? chevronDownUrl : chevronUpUrl} alt="" className="h-4 w-4" />
          </button>
        </div>
        {isPanelOpen && (
          <div className="px-4 py-2 border-t border-gray-200 dark:border-gray-700 space-y-2">
            <ScoreModeIndicator />
            <GameStatusIndicator />
          </div>
        )}
      </div>
      <PanelTabs className={`${!isPanelOpen ? 'md:hidden' : ''}`} />
      <div className={`flex-1 overflow-y-auto p-4 ${isPanelOpen ? '' : 'hidden'}`}>{content}</div>
    </div>
  );
}

import PanelTabs from './PanelTabs';
import PlaneListPanelContent from '../../features/planes/components/PlaneListPanelContent';
import LeaderboardPanelContent from '../../features/leaderboard/components/LeaderboardPanelContent';
import SettingsPanelContent from '../../features/settings/components/SettingsPanelContent';
import { RoomCodeDisplay } from '../ui/RoomCodeDisplay';
import { ScoreModeIndicator } from '../ui/ScoreModeIndicator';
import { GameStatusIndicator } from '../ui/GameStatusIndicator';
import { CurrentHostDisplay } from '../ui/CurrentHostDisplay';
import { MobileStatusBar } from '../ui/MobileStatusBar';
import { MobileGameStatus } from '../ui/MobileGameStatus';
import { useStore } from '../../hooks/useStore';
import {
  selectActivePanel,
  selectIsPanelOpen,
  selectRetroMode,
} from '../../features/ui/selectors';
import chevronUpUrl from '../../assets/icons/chevron-up.svg';
import chevronDownUrl from '../../assets/icons/chevron-down.svg';

export default function SlidingPanel(): JSX.Element {
  const activePanel = useStore(selectActivePanel);
  const isPanelOpen = useStore(selectIsPanelOpen);
  const retroMode = useStore(selectRetroMode);
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

  // Retro panel styling
  // Panel container should NOT scroll - only the content area inside should scroll
  const panelClasses = retroMode
    ? `flex min-h-0 flex-col w-full bg-retro-bg border-l border-retro-border text-retro-text transition-all duration-300 ease-in-out relative z-[700] shadow-[-6px_0_12px_rgba(45,42,36,0.08)] ${isPanelOpen ? 'h-1/2 overflow-hidden md:w-96 md:overflow-hidden' : 'h-16 overflow-hidden md:w-16 md:overflow-hidden'} md:h-full`
    : `flex min-h-0 flex-col w-full bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 transition-all duration-300 ease-in-out relative z-[700] ${isPanelOpen ? 'h-1/2 overflow-hidden md:w-96 md:overflow-hidden' : 'h-16 overflow-hidden md:w-16 md:overflow-hidden'} md:h-full`;

  const headerBorderClasses = retroMode
    ? 'border-b border-retro-border'
    : 'border-b border-gray-700';

  const headerRowClasses = retroMode
    ? 'flex items-center justify-between px-3 py-2 bg-retro-panel-dark'
    : 'flex items-center justify-between p-2';

  const toggleButtonClasses = retroMode
    ? 'p-2 hover:bg-retro-panel text-retro-primary transition-colors'
    : 'p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded';

  const statusSectionClasses = retroMode
    ? 'px-4 py-3 border-t border-retro-border space-y-2 bg-retro-panel'
    : 'px-4 py-2 border-t border-gray-200 dark:border-gray-700 space-y-2';

  const contentClasses = retroMode
    ? `flex-1 min-h-0 p-4 bg-retro-bg ${isPanelOpen ? 'overflow-y-auto overflow-x-hidden overscroll-contain touch-pan-y' : 'hidden'}`
    : `flex-1 min-h-0 p-4 ${isPanelOpen ? 'overflow-y-auto overflow-x-hidden overscroll-contain touch-pan-y' : 'hidden'}`;

  return (
    <div className={panelClasses}>
      {/* Brass corner decoration for retro mode */}
      {retroMode && <div className="brass-corners absolute inset-0 pointer-events-none" />}

      {/* Header section - fixed at top, should not shrink */}
      <div className={`flex-shrink-0 ${headerBorderClasses}`}>
        <div className={headerRowClasses}>
          <RoomCodeDisplay className={isPanelOpen ? '' : 'hidden md:hidden'} />
          <button
            type="button"
            onClick={togglePanelOpen}
            aria-label={isPanelOpen ? 'Minimize panel' : 'Maximize panel'}
            aria-expanded={isPanelOpen}
            className={toggleButtonClasses}
          >
            {retroMode ? (
              <span className="font-splitflap text-lg">{isPanelOpen ? '▼' : '▲'}</span>
            ) : (
              <img src={isPanelOpen ? chevronDownUrl : chevronUpUrl} alt="" className="h-4 w-4" />
            )}
          </button>
        </div>
        {isPanelOpen && (
          <>
            {/* Mobile: Condensed single-line status */}
            <div className={`md:hidden ${statusSectionClasses} !space-y-1 !py-2`}>
              <MobileStatusBar />
              <MobileGameStatus />
            </div>
            {/* Desktop: Full multi-line status */}
            <div className={`hidden md:block ${statusSectionClasses}`}>
              <ScoreModeIndicator />
              <CurrentHostDisplay />
              <GameStatusIndicator />
            </div>
          </>
        )}
      </div>
      {/* Tabs - fixed below header, should not shrink */}
      <PanelTabs className={`flex-shrink-0 ${!isPanelOpen ? 'md:hidden' : ''}`} />
      <div className={contentClasses}>{content}</div>
    </div>
  );
}

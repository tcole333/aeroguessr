import React from 'react';
import { useStore } from '../../hooks/useStore';
import { selectRoomCode, selectPlayerNickname } from '../../features/connection/selectors';
import { selectScores, selectHost, selectIsSoloRoom } from '../../features/game/selectors';
import { selectRetroMode } from '../../features/ui/selectors';

interface MobileStatusBarProps {
  className?: string;
}

/**
 * Condensed single-line status bar for mobile devices.
 * Shows: Room | Mode | Score | Host
 * Only visible on mobile (md:hidden).
 */
export const MobileStatusBar: React.FC<MobileStatusBarProps> = ({ className = '' }) => {
  const roomCode = useStore(selectRoomCode);
  const scoringMode = useStore((s) => s.game.scoringMode);
  const scores = useStore(selectScores);
  const myNickname = useStore(selectPlayerNickname);
  const hostNickname = useStore(selectHost);
  const retroMode = useStore(selectRetroMode);
  const isSolo = useStore(selectIsSoloRoom);

  const myScore = myNickname ? scores[myNickname] || 0 : 0;
  const modeLabel = scoringMode === 'Exact' ? 'Exact' : scoringMode === 'Distance' ? 'Dist' : null;

  // Build status items - only include what's available
  const statusItems: string[] = [];

  if (roomCode && !isSolo) {
    statusItems.push(roomCode);
  } else if (isSolo) {
    statusItems.push('Solo');
  }

  if (modeLabel) {
    statusItems.push(modeLabel);
  }

  if (myNickname) {
    statusItems.push(`${myScore} pts`);
  }

  if (hostNickname && !isSolo) {
    statusItems.push(hostNickname);
  }

  // Don't render if nothing to show
  if (statusItems.length === 0) {
    return null;
  }

  if (retroMode) {
    return (
      <div className={`flex items-center gap-2 text-xs font-display uppercase tracking-wider ${className}`}>
        {statusItems.map((item, index) => (
          <React.Fragment key={item}>
            {index > 0 && <span className="text-retro-text-muted">|</span>}
            <span className="text-retro-text">{item}</span>
          </React.Fragment>
        ))}
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-2 text-xs ${className}`}>
      {statusItems.map((item, index) => (
        <React.Fragment key={item}>
          {index > 0 && <span className="text-gray-400 dark:text-gray-500">|</span>}
          <span className="text-gray-700 dark:text-gray-300 font-medium">{item}</span>
        </React.Fragment>
      ))}
    </div>
  );
};

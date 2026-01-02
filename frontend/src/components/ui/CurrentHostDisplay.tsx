import React from 'react';
import { useStore } from '../../hooks/useStore';
import { selectHost } from '../../features/game/selectors';
import { selectRetroMode } from '../../features/ui/selectors';

interface CurrentHostDisplayProps {
  className?: string;
}

export const CurrentHostDisplay: React.FC<CurrentHostDisplayProps> = ({ className = '' }) => {
  const hostNickname = useStore(selectHost);
  const retroMode = useStore(selectRetroMode);

  if (!hostNickname) {
    return null;
  }

  if (retroMode) {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <span className="text-sm font-display uppercase tracking-wider text-retro-text-muted">Host:</span>
        <span className="px-2 py-1 border border-retro-border text-xs font-display uppercase tracking-wider text-retro-text bg-retro-panel-dark">
          {hostNickname}
        </span>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <span className="text-sm text-gray-600 dark:text-gray-400">Host:</span>
      <span className="px-2 py-1 rounded text-xs font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200">
        {hostNickname}
      </span>
    </div>
  );
};

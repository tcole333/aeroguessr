import React from 'react';
import { useStore } from '../../hooks/useStore';
import { selectHost } from '../../features/game/selectors';
import { HostIndicator } from './HostIndicator';

interface CurrentHostDisplayProps {
  className?: string;
}

export const CurrentHostDisplay: React.FC<CurrentHostDisplayProps> = ({ className = '' }) => {
  const hostNickname = useStore(selectHost);

  if (!hostNickname) {
    return null;
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

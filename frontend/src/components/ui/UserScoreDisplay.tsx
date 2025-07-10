import React from 'react';
import { useStore } from '../../hooks/useStore';
import { selectScores } from '../../features/game/selectors';
import { selectPlayerNickname } from '../../features/connection/selectors';

interface UserScoreDisplayProps {
  className?: string;
}

export const UserScoreDisplay: React.FC<UserScoreDisplayProps> = ({ className = '' }) => {
  const scores = useStore(selectScores);
  const myNickname = useStore(selectPlayerNickname);

  if (!myNickname) {
    return null;
  }

  const myScore = scores[myNickname] || 0;

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <span className="text-sm text-gray-600 dark:text-gray-400">Score:</span>
      <span className="text-sm font-medium text-gray-800 dark:text-gray-200">
        {myScore}
      </span>
    </div>
  );
};

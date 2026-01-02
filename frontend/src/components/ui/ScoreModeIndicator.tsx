import React from 'react';
import { useStore } from '../../hooks/useStore';
import { selectScores } from '../../features/game/selectors';
import { selectPlayerNickname } from '../../features/connection/selectors';
import { selectRetroMode } from '../../features/ui/selectors';

interface ScoreModeIndicatorProps {
  className?: string;
}

export const ScoreModeIndicator: React.FC<ScoreModeIndicatorProps> = ({ className = '' }) => {
  const scoringMode = useStore((s) => s.game.scoringMode);
  const round = useStore((s) => s.game.round);
  const roundTimeout = useStore((s) => s.game.roundTimeout);
  const scores = useStore(selectScores);
  const myNickname = useStore(selectPlayerNickname);
  const retroMode = useStore(selectRetroMode);

  if (!scoringMode) {
    return null;
  }

  const isRoundActive = round?.state === 'guessing';

  if (retroMode) {
    return (
      <div className={`flex items-center gap-4 ${className}`}>
        {/* Scoring Mode */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-display uppercase tracking-wider text-retro-text-muted">Mode:</span>
          <span className={`px-2 py-1 border text-xs font-display uppercase tracking-wider ${
            scoringMode === 'Exact'
              ? 'border-retro-border text-retro-text bg-retro-panel-dark'
              : 'border-retro-border text-retro-text bg-retro-panel-dark'
          }`}>
            {scoringMode === 'Exact' ? 'Exact' : 'Distance'}
          </span>
        </div>

        {/* User Score */}
        {myNickname && (
          <div className="flex items-center gap-2">
            <span className="text-sm font-display uppercase tracking-wider text-retro-text-muted">Score:</span>
            <span className="font-splitflap text-sm font-bold text-retro-led-bright">
              {scores[myNickname] || 0}
            </span>
          </div>
        )}

        {/* Round Timer (when active) */}
        {isRoundActive && roundTimeout && (
          <RoundTimer timeout={roundTimeout} retroMode />
        )}
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-4 ${className}`}>
      {/* Scoring Mode */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-600 dark:text-gray-400">Mode:</span>
        <span className={`px-2 py-1 rounded text-xs font-medium ${
          scoringMode === 'Exact'
            ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200'
            : 'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-200'
        }`}>
          {scoringMode === 'Exact' ? '🎯 Exact' : '📍 Distance'}
        </span>
      </div>

      {/* User Score */}
      {myNickname && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600 dark:text-gray-400">Score:</span>
          <span className="text-sm font-medium text-gray-800 dark:text-gray-200">
            {scores[myNickname] || 0}
          </span>
        </div>
      )}

      {/* Round Timer (when active) */}
      {isRoundActive && roundTimeout && (
        <RoundTimer timeout={roundTimeout} />
      )}
    </div>
  );
};

// Separate timer component to handle countdown
const RoundTimer: React.FC<{ timeout: number; retroMode?: boolean }> = ({ timeout, retroMode }) => {
  const [timeLeft, setTimeLeft] = React.useState(timeout);

  React.useEffect(() => {
    setTimeLeft(timeout); // Reset when timeout changes

    const interval = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [timeout]);

  const isUrgent = timeLeft <= 10;

  if (retroMode) {
    return (
      <div className={`flex items-center gap-2 ${isUrgent ? 'animate-pulse' : ''}`}>
        <span className="text-sm font-display uppercase tracking-wider text-retro-text-muted">Time:</span>
        <span className={`font-splitflap text-sm font-bold ${
          isUrgent ? 'text-retro-accent' : 'text-retro-led'
        }`}>
          {timeLeft}s
        </span>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-2 ${
      isUrgent ? 'animate-pulse' : ''
    }`}>
      <span className="text-sm text-gray-600 dark:text-gray-400">Time:</span>
      <span className={`text-sm font-mono font-medium ${
        isUrgent
          ? 'text-red-600 dark:text-red-400'
          : 'text-gray-800 dark:text-gray-200'
      }`}>
        {timeLeft}s
      </span>
    </div>
  );
};

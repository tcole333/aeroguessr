import React from 'react';
import { useStore } from '../../hooks/useStore';

interface GameStatusIndicatorProps {
  className?: string;
}

export const GameStatusIndicator: React.FC<GameStatusIndicatorProps> = ({ className = '' }) => {
  const round = useStore((s) => s.game.round);
  const roundTimeout = useStore((s) => s.game.roundTimeout);
  const isHost = useStore((s) => s.game.hostNickname === s.connection.nickname);
  const isSolo = useStore((s) => s.game.isSolo);

  // Get phase description based on round state
  const getPhaseDescription = () => {
    if (!round) {
      if (isSolo) {
        return 'Solo Mode - Click any plane to guess';
      }
      return isHost ? 'Select a plane to start round' : 'Waiting for game to start';
    }

    switch (round.state) {
      case 'waiting_for_selection':
        return isHost ? 'Select a plane' : 'Waiting for plane selection';
      case 'guessing':
      case 'accepting_guesses':
        return 'Submit your guess';
      case 'showing_results':
        return 'Round complete';
      default:
        return 'Game in progress';
    }
  };

  // Get phase color based on state
  const getPhaseColor = () => {
    if (!round) return 'text-gray-600 dark:text-gray-400';

    switch (round.state) {
      case 'waiting_for_selection':
        return 'text-blue-600 dark:text-blue-400';
      case 'guessing':
      case 'accepting_guesses':
        return 'text-green-600 dark:text-green-400';
      case 'showing_results':
        return 'text-purple-600 dark:text-purple-400';
      default:
        return 'text-gray-600 dark:text-gray-400';
    }
  };

  const isGuessing = round?.state === 'guessing' || round?.state === 'accepting_guesses';

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      {/* Round Number and Phase */}
      <div className="flex items-center justify-between gap-4">
        {/* Round Number */}
        {round && round.round_number > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600 dark:text-gray-400">Round:</span>
            <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
              {round.round_number}
            </span>
          </div>
        )}

        {/* Phase Description */}
        <div className={`text-sm font-medium ${getPhaseColor()}`}>
          {getPhaseDescription()}
        </div>
      </div>

      {/* Round Timer (when guessing) */}
      {isGuessing && roundTimeout && (
        <div className="flex items-center justify-center">
          <GameTimer timeout={roundTimeout} />
        </div>
      )}
    </div>
  );
};

// Separate timer component to handle countdown
const GameTimer: React.FC<{ timeout: number }> = ({ timeout }) => {
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

  const percentage = (timeLeft / timeout) * 100;
  const isUrgent = timeLeft <= 10;

  return (
    <div className="w-full">
      {/* Time display */}
      <div className={`flex items-center justify-center gap-2 mb-1 ${
        isUrgent ? 'animate-pulse' : ''
      }`}>
        <span className="text-xs text-gray-600 dark:text-gray-400">Time:</span>
        <span className={`text-sm font-mono font-bold ${
          isUrgent
            ? 'text-red-600 dark:text-red-400'
            : 'text-gray-800 dark:text-gray-200'
        }`}>
          {Math.floor(timeLeft / 60)}:{(timeLeft % 60).toString().padStart(2, '0')}
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full transition-all duration-1000 ease-linear rounded-full ${
            isUrgent
              ? 'bg-red-500 dark:bg-red-400'
              : 'bg-green-500 dark:bg-green-400'
          }`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};

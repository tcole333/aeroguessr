import React from 'react';
import { useStore } from '../../hooks/useStore';
import { selectRetroMode } from '../../features/ui/selectors';

interface MobileGameStatusProps {
  className?: string;
}

/**
 * Condensed game phase indicator for mobile.
 * Shows a single line like "SELECT FLIGHT TO BEGIN" or "TRANSMIT YOUR GUESS".
 */
export const MobileGameStatus: React.FC<MobileGameStatusProps> = ({ className = '' }) => {
  const round = useStore((s) => s.game.round);
  const isHost = useStore((s) => s.game.hostNickname === s.connection.nickname);
  const isSolo = useStore((s) => s.game.isSolo);
  const retroMode = useStore(selectRetroMode);

  const getPhaseDescription = () => {
    if (!round) {
      if (isSolo) {
        return 'SELECT ANY FLIGHT';
      }
      return isHost ? 'SELECT FLIGHT TO BEGIN' : 'AWAITING DEPARTURE';
    }

    switch (round.state) {
      case 'waiting_for_selection':
        return isHost ? 'SELECT FLIGHT' : 'AWAITING SELECTION';
      case 'guessing':
      case 'accepting_guesses':
        return 'TRANSMIT YOUR GUESS';
      case 'showing_results':
        return 'ROUND COMPLETE';
      default:
        return 'IN PROGRESS';
    }
  };

  const getPhaseColor = () => {
    if (retroMode) {
      if (!round) return 'text-retro-primary';
      switch (round.state) {
        case 'guessing':
        case 'accepting_guesses':
          return 'text-retro-primary';
        default:
          return 'text-retro-text';
      }
    }

    if (!round) return 'text-gray-600 dark:text-gray-400';
    switch (round.state) {
      case 'guessing':
      case 'accepting_guesses':
        return 'text-green-600 dark:text-green-400';
      default:
        return 'text-gray-600 dark:text-gray-400';
    }
  };

  if (retroMode) {
    return (
      <div className={`text-xs font-display uppercase tracking-wider ${getPhaseColor()} ${className}`}>
        {getPhaseDescription()}
      </div>
    );
  }

  return (
    <div className={`text-xs font-medium ${getPhaseColor()} ${className}`}>
      {getPhaseDescription()}
    </div>
  );
};

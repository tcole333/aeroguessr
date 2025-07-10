import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useStore } from '../../hooks/useStore';

interface RoundResultModalProps {
  autoCloseDelay?: number; // milliseconds, default 8000 (8 seconds)
}

export const RoundResultModal: React.FC<RoundResultModalProps> = ({ autoCloseDelay = 8000 }) => {
  const lastRoundResult = useStore((s) => s.game.lastRoundResult);
  const scoringMode = useStore((s) => s.game.scoringMode);
  const myNickname = useStore((s) => s.connection.nickname);
  const [isVisible, setIsVisible] = useState(false);
  const [isClosing, setIsClosing] = useState(false);

  useEffect(() => {
    if (lastRoundResult) {
      setIsVisible(true);
      setIsClosing(false);

      // Auto-close after delay
      const timer = setTimeout(() => {
        handleClose();
      }, autoCloseDelay);

      return () => clearTimeout(timer);
    }
  }, [lastRoundResult, autoCloseDelay]);

  const handleClose = () => {
    setIsClosing(true);
    setTimeout(() => {
      setIsVisible(false);
    }, 300); // Match animation duration
  };

  if (!isVisible || !lastRoundResult) {
    return null;
  }

  // Find the correct answer from any result
  const correctCode = lastRoundResult.results[0]?.correct_code || 'Unknown';

  // Sort results by score awarded (descending) for leaderboard effect
  const sortedResults = [...lastRoundResult.results].sort(
    (a, b) => b.score_awarded - a.score_awarded
  );

  // Find my result
  const myResult = lastRoundResult.results.find(r => r.nickname === myNickname);

  return createPortal(
    <div
      className={`fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 transition-opacity duration-300 ${
        isClosing ? 'opacity-0' : 'opacity-100'
      }`}
      onClick={handleClose}
    >
      <div
        className={`relative z-[10000] bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-lg w-full mx-4 transform transition-all duration-300 ${
          isClosing ? 'scale-95 opacity-0' : 'scale-100 opacity-100'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-b border-gray-200 dark:border-gray-700 px-6 py-4">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">
            Round Complete!
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Correct answer: <span className="font-semibold text-green-600 dark:text-green-400">{correctCode}</span>
          </p>
        </div>

        {/* Results */}
        <div className="px-6 py-4 max-h-96 overflow-y-auto">
          <div className="space-y-3">
            {sortedResults.map((result, index) => (
              <div
                key={result.nickname}
                className={`flex items-center justify-between p-3 rounded-lg ${
                  result.nickname === myNickname
                    ? 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800'
                    : 'bg-gray-50 dark:bg-gray-700/50'
                }`}
              >
                <div className="flex items-center gap-3">
                  {/* Position indicator */}
                  <div className={`text-lg font-bold ${
                    index === 0 ? 'text-yellow-500' :
                    index === 1 ? 'text-gray-400' :
                    index === 2 ? 'text-orange-600' :
                    'text-gray-600 dark:text-gray-400'
                  }`}>
                    #{index + 1}
                  </div>

                  <div>
                    <div className="font-medium text-gray-900 dark:text-white">
                      {result.nickname}
                      {result.nickname === myNickname && (
                        <span className="ml-2 text-xs text-blue-600 dark:text-blue-400">(You)</span>
                      )}
                    </div>
                    <div className="text-sm text-gray-600 dark:text-gray-400">
                      Guessed: {result.guess || 'No guess'}
                    </div>
                  </div>
                </div>

                <div className="text-right">
                  <div className={`text-lg font-bold ${
                    result.score_awarded > 0
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-gray-500 dark:text-gray-400'
                  }`}>
                    +{result.score_awarded}
                  </div>
                  <div className="text-sm text-gray-600 dark:text-gray-400">
                    Total: {result.current_total_score}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Distance mode additional info */}
          {scoringMode === 'Distance' && myResult && myResult.score_awarded < 100 && (
            <div className="mt-4 p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
              <p className="text-sm text-amber-800 dark:text-amber-200">
                💡 In Distance mode, you get more points the closer your guess is to the correct airport.
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 dark:border-gray-700 px-6 py-4">
          <button
            onClick={handleClose}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-4 rounded-lg transition-colors"
            aria-label="Close round results"
          >
            Continue
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};

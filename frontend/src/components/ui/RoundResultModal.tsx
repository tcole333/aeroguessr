import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useStore } from '../../hooks/useStore';
import { selectRetroMode } from '../../features/ui/selectors';
import { formatAirportDisplay } from '../../lib/airportLookup';

type ModalVariant = 'retro' | 'standard';

/**
 * Distance suffix for a guess, or null when the server sent no usable distance
 * (e.g. distance_km: null for an airport without coordinates).
 */
function formatDistance(distanceKm: number | null | undefined, variant: ModalVariant): string | null {
  if (typeof distanceKm !== 'number') return null;
  if (distanceKm === 0) return variant === 'retro' ? 'Exact' : 'Exact match!';
  const km = distanceKm.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return variant === 'retro' ? `${km}km` : `${km} km away`;
}

interface DistanceNoteProps {
  distanceKm: number | null | undefined;
  variant: ModalVariant;
  className: string;
}

const DistanceNote: React.FC<DistanceNoteProps> = ({ distanceKm, variant, className }) => {
  const label = formatDistance(distanceKm, variant);
  if (label === null) return null;
  return <span className={className}>({label})</span>;
};

interface RoundResultModalProps {
  autoCloseDelay?: number; // milliseconds, default 8000 (8 seconds)
}

export const RoundResultModal: React.FC<RoundResultModalProps> = ({ autoCloseDelay = 8000 }) => {
  const lastRoundResult = useStore((s) => s.game.lastRoundResult);
  const scoringMode = useStore((s) => s.game.scoringMode);
  const myNickname = useStore((s) => s.connection.nickname);
  const retroMode = useStore(selectRetroMode);
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
  const correctCodeRaw = lastRoundResult.results[0]?.correct_code || 'Unknown';
  const correctCode = formatAirportDisplay(correctCodeRaw);

  // Sort results by score awarded (descending) for leaderboard effect
  const sortedResults = [...lastRoundResult.results].sort(
    (a, b) => b.score_awarded - a.score_awarded
  );

  // Find my result
  const myResult = lastRoundResult.results.find(r => r.nickname === myNickname);

  // Retro-themed modal
  if (retroMode) {
    return createPortal(
      <div
        className={`retro-vars fixed inset-0 z-[9999] flex items-center justify-center bg-black/70 transition-opacity duration-300 ${
          isClosing ? 'opacity-0' : 'opacity-100'
        }`}
        onClick={handleClose}
      >
        <div
          className={`relative z-[10000] max-w-lg w-full mx-4 transform transition-all duration-300 ${
            isClosing ? 'scale-95 opacity-0' : 'scale-100 opacity-100'
          }`}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Brass corner decorations */}
          <div className="absolute -top-1 -left-1 w-4 h-4 border-l-2 border-t-2 border-retro-brass" />
          <div className="absolute -top-1 -right-1 w-4 h-4 border-r-2 border-t-2 border-retro-brass" />
          <div className="absolute -bottom-1 -left-1 w-4 h-4 border-l-2 border-b-2 border-retro-brass" />
          <div className="absolute -bottom-1 -right-1 w-4 h-4 border-r-2 border-b-2 border-retro-brass" />

          <div className="bg-retro-panel border border-retro-border shadow-[0_2px_8px_rgba(45,42,36,0.08)]">
            {/* Header with correct answer */}
            <div className="bg-retro-panel-dark border-b border-retro-border px-6 py-4">
              <h2 className="font-display text-sm uppercase tracking-widest text-retro-text-muted mb-2">
                Round Complete
              </h2>
              <div className="flex items-center gap-3">
                <span className="font-display text-xs uppercase tracking-wider text-retro-text-muted">
                  Answer:
                </span>
                <span className="font-splitflap text-2xl text-retro-led-bright tracking-widest">
                  {correctCode}
                </span>
              </div>
            </div>

            {/* Results as departure board rows */}
            <div className="px-4 py-4 max-h-96 overflow-y-auto">
              <div className="space-y-2">
                {sortedResults.map((result, index) => (
                  <div
                    key={result.nickname}
                    className={`flex items-center justify-between p-3 border ${
                      result.nickname === myNickname
                        ? 'bg-retro-panel-dark border-retro-primary'
                        : 'bg-retro-panel-dark border-retro-border'
                    }`}
                  >
                    <div className="flex items-center gap-4">
                      {/* Rank number in splitflap font */}
                      <div className="font-splitflap text-lg text-retro-led w-8">
                        {String(index + 1).padStart(2, '0')}
                      </div>

                      <div>
                        {/* Player name in display font */}
                        <div className="font-display text-sm uppercase tracking-wider text-retro-ink">
                          {result.nickname}
                          {result.nickname === myNickname && (
                            <span className="ml-2 text-xs text-retro-text-muted">(You)</span>
                          )}
                        </div>
                        {/* Their guess */}
                        <div className="font-splitflap text-xs text-retro-led mt-1">
                          {result.guess ? formatAirportDisplay(result.guess) : '---'}
                          {scoringMode === 'Distance' && result.guess && (
                            <DistanceNote
                              distanceKm={result.distance_km}
                              variant="retro"
                              className="ml-2 font-display text-retro-text-muted"
                            />
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Score */}
                    <div className="text-right">
                      <div className={`font-splitflap text-lg ${
                        result.score_awarded > 0
                          ? 'text-retro-success'
                          : 'text-retro-text-muted'
                      }`}>
                        +{result.score_awarded}
                      </div>
                      <div className="font-display text-xs text-retro-text-muted uppercase">
                        Total: {result.current_total_score}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Distance mode tip */}
              {scoringMode === 'Distance' && myResult && myResult.score_awarded < 100 && (
                <div className="mt-4 p-3 bg-retro-panel-dark border border-retro-border">
                  <p className="font-display text-xs text-retro-text-muted uppercase tracking-wider">
                    Distance mode: Closer guesses earn more points
                  </p>
                </div>
              )}
            </div>

            {/* Footer with continue button */}
            <div className="border-t border-retro-border px-6 py-4">
              <button
                onClick={handleClose}
                className="w-full py-3 px-4 font-display text-sm uppercase tracking-widest border-0 bg-retro-primary text-retro-panel hover:bg-retro-primary-bright transition-all"
                aria-label="Close round results"
              >
                Continue
              </button>
            </div>
          </div>
        </div>
      </div>,
      document.body
    );
  }

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
                      Guessed: {result.guess ? formatAirportDisplay(result.guess) : 'No guess'}
                      {scoringMode === 'Distance' && result.guess && (
                        <DistanceNote distanceKm={result.distance_km} variant="standard" className="ml-2" />
                      )}
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

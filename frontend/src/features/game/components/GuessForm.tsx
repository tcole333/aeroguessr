import { useCallback } from 'react';
import { useGuess } from '../hooks/useGuess';
import { AirportAutocomplete } from '../../../components/AirportAutocomplete';
import type { Airport } from '../../../components/AirportAutocomplete';
import { useStore } from '../../../hooks/useStore';
import { selectRetroMode } from '../../ui/selectors';
import { selectRound, selectUsedPlanes } from '../selectors';
import { selectPlaneById } from '../../planes/selectors';
import type { PlaneState } from '../../common/types';
import { formatAirportDisplay } from '../../../lib/airportLookup';

function getFlightStatus(alt_v: number | undefined, alt: number | undefined): string {
  if (!alt_v || !alt) return 'TRACKING';
  if (alt < 3000) return alt_v > 50 ? 'DEPARTING' : 'ARRIVING';
  if (alt_v > 100) return 'ASCENDING';
  if (alt_v < -100) return 'DESCENDING';
  return 'CRUISING';
}

export default function GuessForm(): JSX.Element | null {
  const {
    inputValue,
    selectedAirport,
    disabled,
    error,
    remaining,
    visible,
    setInputValue,
    setSelectedAirport,
    handleSubmit,
    dismiss,
  } = useGuess();

  const retroMode = useStore(selectRetroMode);
  const round = useStore(selectRound);
  const planeHex = round?.hex;
  const plane = useStore(selectPlaneById(planeHex ?? '')) as PlaneState | undefined;
  const usedPlanes = useStore(selectUsedPlanes);

  // Determine what's hidden based on round direction
  // direction === 'origin' means we're guessing origin, so hide origin
  // direction === 'destination' means we're guessing destination, so hide destination
  const isRoundComplete = planeHex ? usedPlanes.has(planeHex) && round?.state !== 'guessing' : false;
  const guessDirection = round?.direction;

  // Determine what to show for origin/destination
  const getDisplayValue = (field: 'origin' | 'destination'): string | null => {
    if (!plane) return null;
    const value = field === 'origin' ? plane.origin : plane.destination;

    // After round is complete, show the actual value
    if (isRoundComplete) return value ? formatAirportDisplay(value) : null;

    // During active round, hide the field being guessed
    if (guessDirection === field) return null; // Hide - return null to not render

    return value ? formatAirportDisplay(value) : null;
  };

  // Get header text based on direction
  const headerText = guessDirection === 'origin' ? 'ORIGIN' : 'DESTINATION';

  const handleAirportChange = useCallback((value: string) => {
    setInputValue(value);
    // Clear selected airport if user modifies the input
    if (selectedAirport && value !== selectedAirport.iata && value !== selectedAirport.icao) {
      setSelectedAirport(null);
    }
  }, [selectedAirport, setInputValue, setSelectedAirport]);

  const handleAirportSelect = useCallback((airport: Airport) => {
    setSelectedAirport(airport);
    // Don't call setInputValue here - the AirportAutocomplete component
    // already updates its own input value in handleSelectAirport
  }, [setSelectedAirport]);

  if (!visible) return null;

  // Retro mode rendering
  if (retroMode) {
    const flightStatus = getFlightStatus(plane?.alt_v, plane?.alt);

    return (
      <div
        className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/70"
        onClick={dismiss}
        role="dialog"
        aria-modal="true"
      >
        <div
          onClick={(e) => e.stopPropagation()}
          className="w-full max-w-md relative"
        >
          {/* Brass corner decorations */}
          <div className="absolute -top-1 -left-1 w-4 h-4 border-l-2 border-t-2 border-retro-brass" />
          <div className="absolute -top-1 -right-1 w-4 h-4 border-r-2 border-t-2 border-retro-brass" />
          <div className="absolute -bottom-1 -left-1 w-4 h-4 border-l-2 border-b-2 border-retro-brass" />
          <div className="absolute -bottom-1 -right-1 w-4 h-4 border-r-2 border-b-2 border-retro-brass" />

          <form
            onSubmit={handleSubmit}
            className="bg-retro-panel border border-retro-border p-6 space-y-4"
          >
            {/* Header with time remaining */}
            <div className="flex items-center justify-between border-b border-retro-border pb-4">
              <h2 className="font-splitflap text-xl text-retro-led tracking-widest">
                {headerText}
              </h2>
              {remaining != null && (
                <div className="font-splitflap text-lg text-retro-led-bright">
                  {remaining}
                </div>
              )}
            </div>

            {/* Plane info section */}
            <div className="bg-retro-panel-dark border border-retro-border p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-display text-xs text-retro-text-muted uppercase tracking-wider">
                  Flight
                </span>
                <span className="font-splitflap text-retro-led tracking-wider">
                  {plane?.callsign || planeHex || 'UNKNOWN'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-display text-xs text-retro-text-muted uppercase tracking-wider">
                  Status
                </span>
                <span className="font-splitflap text-retro-led tracking-wider">
                  {flightStatus}
                </span>
              </div>
              {plane?.alt != null && (
                <div className="flex items-center justify-between">
                  <span className="font-display text-xs text-retro-text-muted uppercase tracking-wider">
                    Altitude
                  </span>
                  <span className="font-splitflap text-retro-led tracking-wider">
                    {Math.round(plane.alt).toLocaleString()} FT
                  </span>
                </div>
              )}
              {/* Show origin - conditionally hidden if that's what we're guessing */}
              {getDisplayValue('origin') && (
                <div className="flex items-center justify-between">
                  <span className="font-display text-xs text-retro-text-muted uppercase tracking-wider">
                    Origin
                  </span>
                  <span className="font-splitflap text-retro-led tracking-wider">
                    {getDisplayValue('origin')}
                  </span>
                </div>
              )}
              {/* Show destination - conditionally hidden if that's what we're guessing */}
              {getDisplayValue('destination') && (
                <div className="flex items-center justify-between">
                  <span className="font-display text-xs text-retro-text-muted uppercase tracking-wider">
                    Destination
                  </span>
                  <span className="font-splitflap text-retro-led tracking-wider">
                    {getDisplayValue('destination')}
                  </span>
                </div>
              )}
              {plane?.operator && (
                <div className="flex items-center justify-between">
                  <span className="font-display text-xs text-retro-text-muted uppercase tracking-wider">
                    Airline
                  </span>
                  <span className="font-display text-retro-text tracking-wider">
                    {plane.operator}
                  </span>
                </div>
              )}
            </div>

            {/* Airport input */}
            <div>
              <label htmlFor="airport-guess" className="block font-display text-xs text-retro-text-muted uppercase tracking-wider mb-2">
                Enter {headerText}
              </label>
              <AirportAutocomplete
                id="airport-guess"
                value={inputValue}
                onChange={handleAirportChange}
                onSelect={handleAirportSelect}
                placeholder="Type city or airport code..."
                disabled={disabled}
                className="w-full"
                inputClassName="!font-display !normal-case !tracking-[0.06em] !text-retro-ink"
                aria-label="Airport guess"
                aria-describedby={error ? "guess-error" : undefined}
                autoFocus
                retroMode
              />
              {selectedAirport && (
                <p className="mt-2 font-display text-xs text-retro-text">
                  Selected: {selectedAirport.name} ({selectedAirport.iata || selectedAirport.icao})
                </p>
              )}
            </div>

            {/* Error message */}
            {error && (
              <p id="guess-error" className="font-display text-sm text-retro-accent" role="alert">
                {error}
              </p>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={disabled}
              className="w-full py-3 px-4 font-display text-sm uppercase tracking-widest bg-retro-primary text-retro-panel border-0 hover:bg-retro-primary-bright transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {disabled ? 'Transmitted' : 'Transmit Guess'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  // Standard mode rendering
  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50"
      onClick={dismiss}
      role="dialog"
      aria-modal="true"
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="space-y-3 rounded-lg bg-white p-6 shadow-xl dark:bg-gray-800 min-w-[320px] max-w-[90vw]"
      >
        <div>
          <label htmlFor="airport-guess" className="block text-sm font-medium mb-2">
            Guess the {guessDirection === 'origin' ? 'origin' : 'destination'} {remaining != null && <span className="text-gray-500">({remaining})</span>}
          </label>
          <AirportAutocomplete
            id="airport-guess"
            value={inputValue}
            onChange={handleAirportChange}
            onSelect={handleAirportSelect}
            placeholder="Type city or airport code..."
            disabled={disabled}
            className="w-full"
            aria-label="Airport guess"
            aria-describedby={error ? "guess-error" : undefined}
            autoFocus
          />
          {selectedAirport && (
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
              Selected: {selectedAirport.name} ({selectedAirport.iata || selectedAirport.icao})
            </p>
          )}
        </div>

        {error && (
          <p id="guess-error" className="text-sm text-red-500" role="alert">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={disabled}
          className="w-full rounded-lg bg-blue-500 px-4 py-2 text-white font-medium hover:bg-blue-600 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          {disabled ? 'Guess Submitted' : 'Submit Guess'}
        </button>
      </form>
    </div>
  );
}

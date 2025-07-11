import React, { useCallback } from 'react';
import { useGuess } from '../hooks/useGuess';
import { AirportAutocomplete } from '../../../components/AirportAutocomplete';
import type { Airport } from '../../../components/AirportAutocomplete';

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
            Where is this flight {remaining != null && <span className="text-gray-500">({remaining}s)</span>}
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

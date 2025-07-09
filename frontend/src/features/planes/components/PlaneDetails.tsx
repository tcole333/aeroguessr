import { useState, useEffect } from 'react';
import { useStore } from '../../../hooks/useStore';
import { webSocketClient } from '../../../hooks/useWebSocketManager';
import { selectPlaneById } from '../selectors';
import {
  selectHost,
  selectIsSolo,
  selectSelectedPlane,
  selectGuessDirection,
  selectRound,
  selectRoundTimeout,
  selectUsedPlanes
} from '../../game/selectors';
import {
  selectPlayerNickname,
  selectConnectionStatus,
} from '../../connection/selectors';
import type { PlaneState } from '../../common/types';

interface PlaneDetailsProps {
  hex: string;
  onClose: () => void;
}

export default function PlaneDetails({ hex, onClose }: PlaneDetailsProps): JSX.Element {
  const plane = useStore(selectPlaneById(hex));
  const host = useStore(selectHost);
  const isSolo = useStore(selectIsSolo);
  const myNick = useStore(selectPlayerNickname);
  const status = useStore(selectConnectionStatus);
  const selectedPlane = useStore(selectSelectedPlane);
  const guessDirection = useStore(selectGuessDirection);
  const round = useStore(selectRound);
  const roundTimeout = useStore(selectRoundTimeout);
  const usedPlanes = useStore(selectUsedPlanes);

  const [guessCode, setGuessCode] = useState('');
  const [hasGuessed, setHasGuessed] = useState(false);
  const [guessError, setGuessError] = useState<string | null>(null);
  const [remainingTime, setRemainingTime] = useState<number | null>(null);

  const isHost = !isSolo && host && myNick === host;
  const isSelected = selectedPlane === hex;
  const isRoundActive = round?.state === 'guessing' && round?.hex === hex;
  const isUsed = usedPlanes.has(hex);
  const canSelectPlane = isHost && status === 'connected' && !isRoundActive && !isUsed;
  const canStartRound = isHost && status === 'connected' && isSelected && !isRoundActive;
  const canGuess = status === 'connected' && isRoundActive && !hasGuessed;

  // Determine which airport should be hidden based on the same logic as backend
  // TODO: Get monitored airport from configuration instead of hardcoding
  const monitoredAirport = 'KBOS';
  const determineGuessDirection = (plane: PlaneState): string | null => {
    if (!plane.origin || !plane.destination) return null;

    // Same logic as backend: if origin matches monitored airport, guess destination
    if (plane.origin === monitoredAirport) {
      return 'destination';
    }
    // If destination matches monitored airport, guess origin
    if (plane.destination === monitoredAirport) {
      return 'origin';
    }
    return null;
  };

  const shouldHideAirport = determineGuessDirection(plane);


  // Reset guess state when round changes
  useEffect(() => {
    if (isRoundActive) {
      setGuessCode('');
      setHasGuessed(false);
      setGuessError(null);

      // Start countdown timer
      if (roundTimeout) {
        const end = Date.now() + roundTimeout * 1000;
        setRemainingTime(roundTimeout);
        const timer = setInterval(() => {
          const left = Math.max(0, Math.ceil((end - Date.now()) / 1000));
          setRemainingTime(left);
          if (left === 0) {
            clearInterval(timer);
          }
        }, 1000);
        return () => clearInterval(timer);
      }
    } else {
      setRemainingTime(null);
    }
    return undefined;
  }, [round, roundTimeout, isRoundActive]);

  if (!plane) {
    return (
      <div className="p-4 border-t border-gray-700">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold">Plane Details</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white"
            aria-label="Close details"
          >
            ×
          </button>
        </div>
        <p className="text-gray-400">Plane not found</p>
      </div>
    );
  }

  const handleSelectPlane = () => {
    if (!canSelectPlane) return;

    try {
      webSocketClient.send({ type: 'selectPlane', payload: { hex } });
    } catch (err) {
      console.error('Failed to select plane:', err);
    }
  };

  const handleStartRound = () => {
    if (!canStartRound) return;

    try {
      webSocketClient.send({ type: 'startRound', payload: {} });
    } catch (err) {
      console.error('Failed to start round:', err);
    }
  };

  const handleGuessSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canGuess) return;

    const trimmed = guessCode.trim().toUpperCase();
    if (!trimmed) {
      setGuessError('Airport code required');
      return;
    }

    try {
      webSocketClient.send({ type: 'guess', payload: { airport_code: trimmed } });
      setHasGuessed(true);
      setGuessError(null);
    } catch (err) {
      setGuessError((err as Error).message);
    }
  };

  const formatAltitude = (alt: number) => {
    return `${alt.toLocaleString()} ft`;
  };

  const formatSpeed = (latV: number, lonV: number) => {
    // Basic speed calculation from velocity components
    const speedKts = Math.sqrt(latV * latV + lonV * lonV) * 3600 * 60; // rough conversion
    return `${Math.round(speedKts)} kts`;
  };

  return (
    <div className="border-t border-gray-700 bg-gray-800">
      <div className="p-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-white">
            {plane.callsign || plane.hex_ident}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-xl"
            aria-label="Close details"
          >
            ×
          </button>
        </div>

        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-gray-400">Hex ID:</span>
              <p className="text-white font-mono">{plane.hex_ident}</p>
            </div>
            <div>
              <span className="text-gray-400">Callsign:</span>
              <p className="text-white">{plane.callsign || 'Unknown'}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-gray-400">Altitude:</span>
              <p className="text-white">{formatAltitude(plane.alt)}</p>
            </div>
            <div>
              <span className="text-gray-400">Speed:</span>
              <p className="text-white">{formatSpeed(plane.lat_v, plane.lon_v)}</p>
            </div>
          </div>

          {/* Show origin/destination based on game state */}
          <div className="grid grid-cols-2 gap-4">
            {/* Show origin - hide if this is the airport we would be guessing */}
            {shouldHideAirport !== 'origin' && (
              <div>
                <span className="text-gray-400">Origin:</span>
                <p className="text-white">{plane.origin || 'Unknown'}</p>
              </div>
            )}

            {/* Show destination - hide if this is the airport we would be guessing */}
            {shouldHideAirport !== 'destination' && (
              <div>
                <span className="text-gray-400">Destination:</span>
                <p className="text-white">{plane.destination || 'Unknown'}</p>
              </div>
            )}
          </div>

          {plane.origin_country && (
            <div>
              <span className="text-gray-400">Country:</span>
              <p className="text-white">{plane.origin_country}</p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-gray-400">Latitude:</span>
              <p className="text-white font-mono">{plane.lat.toFixed(4)}</p>
            </div>
            <div>
              <span className="text-gray-400">Longitude:</span>
              <p className="text-white font-mono">{plane.lon.toFixed(4)}</p>
            </div>
          </div>
        </div>

        {/* Host Controls */}
        {isHost && (
          <div className="mt-6 space-y-3">
            <div className="border-t border-gray-600 pt-4">
              <h4 className="text-sm font-medium text-gray-300 mb-3">Host Controls</h4>

              {isSelected && !isUsed && (
                <div className="mb-3 p-2 bg-blue-900 rounded border border-blue-600">
                  <p className="text-sm text-blue-200">✓ Selected for round</p>
                </div>
              )}

              {isUsed && !isRoundActive && (
                <div className="mb-3 p-2 bg-gray-800 rounded border border-gray-600">
                  <p className="text-sm text-gray-300">✓ This plane has already been used in a previous round</p>
                </div>
              )}

              <div className="space-y-2">
                <button
                  type="button"
                  onClick={handleSelectPlane}
                  disabled={!canSelectPlane}
                  className={`w-full rounded py-2 px-3 text-white transition-colors ${
                    isSelected && !isUsed
                      ? 'bg-green-600 hover:bg-green-700'
                      : isUsed
                      ? 'bg-gray-500 cursor-not-allowed'
                      : 'bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400'
                  }`}
                >
                  {isUsed ? 'Already Used' : isSelected ? 'Selected' : 'Select for Round'}
                </button>

                <button
                  type="button"
                  onClick={handleStartRound}
                  disabled={!canStartRound}
                  className="w-full rounded bg-green-500 py-2 px-3 text-white disabled:bg-gray-400 hover:bg-green-600"
                >
                  Start Round
                </button>
              </div>
            </div>
          </div>
        )}


        {/* Guess Form */}
        {isRoundActive ? (
          <div className="mt-6 space-y-3">
            <div className="border-t border-gray-600 pt-4">
              <h4 className="text-sm font-medium text-gray-300 mb-3">
                Guess the {round.direction === 'destination' ? 'destination' : 'origin'} airport
              </h4>

              {remainingTime !== null && (
                <div className="mb-3 p-2 bg-yellow-900 rounded border border-yellow-600">
                  <p className="text-sm text-yellow-200">
                    Time remaining: {remainingTime}s
                  </p>
                </div>
              )}

              <form onSubmit={handleGuessSubmit} className="space-y-3">
                <div>
                  <label htmlFor="guess-input" className="block text-sm text-gray-300 mb-1">
                    Airport Code (e.g., LAX, JFK)
                  </label>
                  <input
                    id="guess-input"
                    type="text"
                    maxLength={4}
                    value={guessCode}
                    onChange={(e) => setGuessCode(e.target.value.toUpperCase())}
                    disabled={!canGuess}
                    className="w-full border border-gray-600 bg-gray-700 text-white p-2 rounded focus:border-blue-500 focus:outline-none"
                    placeholder="Enter code"
                  />
                </div>

                {guessError && (
                  <p className="text-sm text-red-400">{guessError}</p>
                )}

                <button
                  type="submit"
                  disabled={!canGuess}
                  className="w-full rounded bg-blue-500 py-2 px-3 text-white disabled:bg-gray-400 hover:bg-blue-600"
                >
                  {hasGuessed ? 'Guess Submitted' : 'Submit Guess'}
                </button>
              </form>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

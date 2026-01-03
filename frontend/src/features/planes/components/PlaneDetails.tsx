import { useState, useEffect } from 'react';
import { useStore } from '../../../hooks/useStore';
import { webSocketClient } from '../../../hooks/useWebSocketManager';
import { selectPlaneById } from '../selectors';
import {
  selectHost,
  selectIsSolo,
  selectSelectedPlane,
  selectRound,
  selectRoundTimeout,
  selectUsedPlanes
} from '../../game/selectors';
import {
  selectPlayerNickname,
  selectConnectionStatus,
} from '../../connection/selectors';
import { selectRetroMode } from '../../ui/selectors';
import { formatAirportDisplay } from '../../../lib/airportLookup';

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
  const round = useStore(selectRound);
  const roundTimeout = useStore(selectRoundTimeout);
  const usedPlanes = useStore(selectUsedPlanes);
  const retroMode = useStore(selectRetroMode);

  const [guessCode, setGuessCode] = useState('');
  const [hasGuessed, setHasGuessed] = useState(false);
  const [guessError, setGuessError] = useState<string | null>(null);
  const [remainingTime, setRemainingTime] = useState<number | null>(null);

  // In solo mode, the player is always the host; in multiplayer, check nickname
  const isHost = isSolo || (host && myNick === host);
  const isSelected = selectedPlane === hex;
  const isRoundActive = round?.state === 'guessing' && round?.hex === hex;
  const isUsed = usedPlanes.has(hex);
  const canSelectPlane = isHost && status === 'connected' && !isRoundActive && !isUsed;
  const canStartRound = isHost && status === 'connected' && isSelected && !isRoundActive;
  const canGuess = status === 'connected' && isRoundActive && !hasGuessed;

  // Determine which airport to hide based on round direction and game state
  // - During active round for this plane: hide the answer being guessed
  // - After round completes (plane in usedPlanes and no active round): show both
  // - For other planes or before any round: use fallback logic from backend
  const getFieldToHide = (): 'origin' | 'destination' | null => {
    // If this plane was used in a round and round is complete, show both
    if (isUsed && !isRoundActive) {
      return null; // Show both airports
    }

    // During active round on this plane, hide based on direction
    if (isRoundActive && round?.direction) {
      return round.direction as 'origin' | 'destination';
    }

    // For other cases (plane not selected, or before round starts),
    // use fallback logic to prevent accidental spoilers
    // TODO: Get monitored airport from configuration instead of hardcoding
    const monitoredAirport = 'KBOS';
    if (!plane.origin || !plane.destination) return null;

    if (plane.origin === monitoredAirport) {
      return 'destination';
    }
    if (plane.destination === monitoredAirport) {
      return 'origin';
    }
    return null;
  };

  const fieldToHide = getFieldToHide();


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
      <div className={retroMode ? 'p-4 border-t border-retro-border bg-retro-panel' : 'p-4 border-t border-gray-700'}>
        <div className="flex justify-between items-center mb-4">
          <h3 className={retroMode ? 'text-lg font-display font-semibold text-retro-ink uppercase tracking-wider' : 'text-lg font-semibold'}>
            {retroMode ? 'FLIGHT DATA' : 'Plane Details'}
          </h3>
          <button
            onClick={onClose}
            className={retroMode ? 'text-retro-primary hover:text-retro-primary-dark text-xl' : 'text-gray-400 hover:text-white'}
            aria-label="Close details"
          >
            ×
          </button>
        </div>
        <p className={retroMode ? 'text-retro-text font-display' : 'text-gray-400'}>
          {retroMode ? 'FLIGHT NOT FOUND' : 'Plane not found'}
        </p>
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

  const formatAltitudeValue = (alt: number) => {
    return alt.toLocaleString();
  };

  const formatSpeedValue = (latV: number, lonV: number) => {
    // Speed calculation from velocity components
    // Velocities are in degrees/second
    // At equator: 1 degree ≈ 60 nautical miles
    // Speed in degrees/second * 60 nm/degree * 3600 seconds/hour = knots
    // But this needs latitude correction (cosine factor)
    const speedDegPerSec = Math.sqrt(latV * latV + lonV * lonV);
    const speedKts = speedDegPerSec * 60 * 3600; // Approximate, assumes equator

    // Sanity check - aircraft don't fly faster than ~700 knots
    if (speedKts > 1000) {
      return null;
    }

    return `${Math.round(speedKts)}`;
  };

  const altitudeTrend = (altV?: number) => {
    if (altV == null) return { symbol: '•', className: 'text-retro-text-light' };
    if (altV > 50) return { symbol: '▲', className: 'text-retro-success' };
    if (altV < -50) return { symbol: '▼', className: 'text-retro-primary' };
    return { symbol: '•', className: 'text-retro-text-light' };
  };

  // Retro style classes
  const containerClass = retroMode
    ? 'border-t border-retro-border bg-retro-panel text-retro-text font-display'
    : 'border-t border-gray-700 bg-gray-800';

  const headerClass = retroMode
    ? 'font-splitflap text-xl text-retro-led tracking-widest'
    : 'text-lg font-semibold text-white';

  const closeButtonClass = retroMode
    ? 'text-retro-primary hover:text-retro-primary-dark text-xl font-bold'
    : 'text-gray-400 hover:text-white text-xl';

  const labelClass = retroMode
    ? 'text-xs uppercase tracking-widest text-retro-sage'
    : 'text-gray-400';

  // Monospace font style for retro labels
  const labelStyle = retroMode
    ? { fontFamily: "'IBM Plex Sans', 'DM Sans', system-ui, sans-serif" }
    : undefined;

  const valueClass = retroMode
    ? 'font-splitflap text-retro-led tracking-wider'
    : 'text-white';

  const textValueClass = retroMode
    ? 'font-display text-retro-text'
    : 'text-white';

  const altTrend = altitudeTrend(plane.alt_v);

  return (
    <div className={containerClass}>
      <div className="p-4">
        <div className="flex justify-between items-center mb-4">
          <div className={headerClass} role="heading" aria-level={3}>
            {(plane.callsign || plane.hex_ident).toUpperCase()}
          </div>
          <button
            onClick={onClose}
            className={closeButtonClass}
            aria-label="Close details"
          >
            ×
          </button>
        </div>

        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-1 xs:grid-cols-2 gap-4">
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'HEX' : 'Hex ID:'}</span>
              <p className={valueClass}>{plane.hex_ident}</p>
            </div>
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'CALLSIGN' : 'Callsign:'}</span>
              <p className={valueClass}>{(plane.callsign || 'UNKNOWN').toUpperCase()}</p>
            </div>
          </div>

          {plane.operator && (
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'AIRLINE' : 'Airline:'}</span>
              <p className={textValueClass}>{plane.operator}</p>
            </div>
          )}

          <div className="grid grid-cols-1 xs:grid-cols-2 gap-4">
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'ALT' : 'Altitude:'}</span>
              {retroMode ? (
                <p className="flex items-baseline gap-2">
                  <span className={`text-xs ${altTrend.className}`} aria-hidden="true">
                    {altTrend.symbol}
                  </span>
                  <span className={valueClass}>{formatAltitudeValue(plane.alt)}</span>
                  <span className="text-xs font-display text-retro-text-muted">FT</span>
                </p>
              ) : (
                <p className={valueClass}>{`${formatAltitudeValue(plane.alt)} ft`}</p>
              )}
            </div>
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'SPD' : 'Speed:'}</span>
              {retroMode ? (
                <p className="flex items-baseline gap-2">
                  <span className="font-splitflap text-retro-success tracking-wider">
                    {formatSpeedValue(plane.lat_v, plane.lon_v) ?? '---'}
                  </span>
                  <span className="text-xs font-display text-retro-text-muted">KTS</span>
                </p>
              ) : (
                <p className={valueClass}>{`${formatSpeedValue(plane.lat_v, plane.lon_v) ?? 'Invalid'} kts`}</p>
              )}
            </div>
          </div>

          {/* Show origin/destination based on game state */}
          <div className="grid grid-cols-1 xs:grid-cols-2 gap-4">
            {/* Origin - show "???" if hidden, actual value otherwise */}
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'ORIGIN' : 'Origin:'}</span>
              <p className={valueClass}>
                {fieldToHide === 'origin' ? '???' : formatAirportDisplay(plane.origin).toUpperCase()}
              </p>
            </div>

            {/* Destination - show "???" if hidden, actual value otherwise */}
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'DEST' : 'Destination:'}</span>
              <p className={valueClass}>
                {fieldToHide === 'destination' ? '???' : formatAirportDisplay(plane.destination).toUpperCase()}
              </p>
            </div>
          </div>

          {plane.origin_country && (
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'COUNTRY' : 'Country:'}</span>
              <p className={textValueClass}>{plane.origin_country}</p>
            </div>
          )}

          <div className="grid grid-cols-1 xs:grid-cols-2 gap-4">
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'LAT' : 'Latitude:'}</span>
              <p className={valueClass}>{plane.lat.toFixed(4)}</p>
            </div>
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'LON' : 'Longitude:'}</span>
              <p className={valueClass}>{plane.lon.toFixed(4)}</p>
            </div>
          </div>
        </div>

        {/* Host Controls */}
        {isHost && (
          <div className="mt-6 space-y-3">
            <div className={retroMode ? 'border-t border-retro-border pt-4' : 'border-t border-gray-600 pt-4'}>
              <h4 className={retroMode ? 'text-xs font-display uppercase tracking-widest text-retro-text-muted mb-3' : 'text-sm font-medium text-gray-300 mb-3'}>
                {retroMode ? 'GATE CONTROL' : 'Host Controls'}
              </h4>

              {isSelected && !isUsed && (
                <div className={retroMode ? 'mb-3 p-2 border border-retro-primary bg-retro-panel-dark' : 'mb-3 p-2 bg-blue-900 rounded border border-blue-600'}>
                  <p className={retroMode ? 'text-sm font-display text-retro-primary uppercase tracking-wider' : 'text-sm text-blue-200'}>
                    {retroMode ? '✓ FLIGHT SELECTED' : '✓ Selected for round'}
                  </p>
                </div>
              )}

              {isUsed && !isRoundActive && (
                <div className={retroMode ? 'mb-3 p-2 border border-retro-border bg-retro-panel opacity-70' : 'mb-3 p-2 bg-gray-800 rounded border border-gray-600'}>
                  <p className={retroMode ? 'text-sm font-display text-retro-text-muted uppercase tracking-wider' : 'text-sm text-gray-300'}>
                    {retroMode ? '✓ FLIGHT DEPARTED' : '✓ This plane has already been used in a previous round'}
                  </p>
                </div>
              )}

              <div className="space-y-2">
                <button
                  type="button"
                  onClick={handleSelectPlane}
                  disabled={!canSelectPlane}
                  className={retroMode
                    ? `w-full py-3 px-3 font-display uppercase tracking-widest text-sm transition-all border-2 ${
                        isSelected && !isUsed
                          ? 'border-retro-primary bg-retro-panel-dark text-retro-primary'
                          : isUsed
                          ? 'border-retro-border bg-retro-panel text-retro-text-muted cursor-not-allowed'
                          : 'border-retro-primary bg-transparent text-retro-primary hover:bg-retro-panel-dark disabled:opacity-50'
                      }`
                    : `w-full rounded py-2 px-3 text-white transition-colors ${
                        isSelected && !isUsed
                          ? 'bg-green-600 hover:bg-green-700'
                          : isUsed
                          ? 'bg-gray-500 cursor-not-allowed'
                          : 'bg-blue-500 hover:bg-blue-600 disabled:bg-gray-400'
                      }`
                  }
                >
                  {isUsed ? (retroMode ? 'DEPARTED' : 'Already Used') : isSelected ? (retroMode ? 'SELECTED' : 'Selected') : (retroMode ? 'SELECT FLIGHT' : 'Select for Round')}
                </button>

                <button
                  type="button"
                  onClick={handleStartRound}
                  disabled={!canStartRound}
                  className={retroMode
                    ? 'w-full py-3 px-3 font-display uppercase tracking-widest text-sm border-0 bg-retro-primary text-retro-panel hover:bg-retro-primary-bright disabled:opacity-50 transition-all'
                    : 'w-full rounded bg-green-500 py-2 px-3 text-white disabled:bg-gray-400 hover:bg-green-600'
                  }
                >
                  {retroMode ? 'BEGIN ROUND' : 'Start Round'}
                </button>
              </div>
            </div>
          </div>
        )}


        {/* Guess Form */}
        {isRoundActive ? (
          <div className="mt-6 space-y-3">
            <div className={retroMode ? 'border-t border-retro-border pt-4' : 'border-t border-gray-600 pt-4'}>
              <h4 className={retroMode ? 'text-xs font-display uppercase tracking-widest text-retro-text-muted mb-3' : 'text-sm font-medium text-gray-300 mb-3'}>
                {retroMode
                  ? `ENTER ${round.direction === 'destination' ? 'DESTINATION' : 'ORIGIN'} CODE`
                  : `Guess the ${round.direction === 'destination' ? 'destination' : 'origin'} airport`}
              </h4>

              {remainingTime !== null && (
                <div className={retroMode
                  ? 'mb-3 p-3 border border-retro-accent bg-retro-panel-dark'
                  : 'mb-3 p-2 bg-yellow-900 rounded border border-yellow-600'
                }>
                  <p className={retroMode
                    ? 'font-splitflap text-lg text-retro-accent tracking-widest text-center animate-glow-pulse'
                    : 'text-sm text-yellow-200'
                  }>
                    {retroMode ? `00:${remainingTime.toString().padStart(2, '0')}` : `Time remaining: ${remainingTime}s`}
                  </p>
                </div>
              )}

              <form onSubmit={handleGuessSubmit} className="space-y-3">
                <div>
                  <label
                    htmlFor="guess-input"
                    className={retroMode
                      ? 'block text-xs font-display uppercase tracking-widest text-retro-text-muted mb-2'
                      : 'block text-sm text-gray-300 mb-1'
                    }
                  >
                    {retroMode ? 'AIRPORT CODE' : 'Airport Code (e.g., LAX, JFK)'}
                  </label>
                  <input
                    id="guess-input"
                    type="text"
                    maxLength={4}
                    value={guessCode}
                    onChange={(e) => setGuessCode(e.target.value.toUpperCase())}
                    disabled={!canGuess}
                    className={retroMode
                      ? 'w-full border border-retro-border bg-retro-panel text-retro-ink font-display text-xl text-center tracking-[0.2em] p-3 focus:border-retro-primary focus:outline-none uppercase placeholder:text-retro-text-muted'
                      : 'w-full border border-gray-600 bg-gray-700 text-white p-2 rounded focus:border-blue-500 focus:outline-none'
                    }
                    placeholder={retroMode ? '----' : 'Enter code'}
                  />
                </div>

                {guessError && (
                  <p className={retroMode ? 'text-sm font-display text-retro-accent uppercase tracking-wider' : 'text-sm text-red-400'}>
                    {guessError}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={!canGuess}
                  className={retroMode
                    ? 'w-full py-3 px-3 font-display uppercase tracking-widest text-sm border-0 bg-retro-primary text-retro-panel hover:bg-retro-primary-bright disabled:opacity-50 transition-all'
                    : 'w-full rounded bg-blue-500 py-2 px-3 text-white disabled:bg-gray-400 hover:bg-blue-600'
                  }
                >
                  {hasGuessed ? (retroMode ? 'TRANSMITTED' : 'Guess Submitted') : (retroMode ? 'TRANSMIT' : 'Submit Guess')}
                </button>
              </form>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

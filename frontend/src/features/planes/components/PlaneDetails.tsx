import { useState, useEffect } from 'react';
import { useStore } from '../../../hooks/useStore';
import { webSocketClient } from '../../../hooks/useWebSocketManager';
import { selectPlaneById } from '../selectors';
import { getRouteDisplay } from '../routeDisplay';
import { LEVEL_FLIGHT_MAX_FPM } from '../verticalRate';
import {
  selectGuessRejection,
  selectHost,
  selectIsSolo,
  selectRevealedAnswer,
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
import { formatAirportDisplay, guessCodeError } from '../../../lib/airportLookup';

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
  const revealedAnswer = useStore(selectRevealedAnswer(hex));
  const retroMode = useStore(selectRetroMode);
  const guessRejection = useStore(selectGuessRejection);
  const setGuessRejection = useStore((s) => s.game.setGuessRejection);

  const [guessCode, setGuessCode] = useState('');
  const [hasGuessed, setHasGuessed] = useState(false);
  const [guessError, setGuessError] = useState<string | null>(null);
  const [remainingTime, setRemainingTime] = useState<number | null>(null);
  const [startWhenSelected, setStartWhenSelected] = useState(false);

  // In solo mode, the player is always the host; in multiplayer, check nickname
  const isHost = isSolo || (host && myNick === host);
  const isSelected = selectedPlane === hex;
  const isRoundActive = round?.state === 'guessing' && round?.hex === hex;
  const isUsed = usedPlanes.has(hex);
  // The server never sends the guessed end of a route; it is shown only once a
  // roundResult for this plane has revealed it.
  const route = getRouteDisplay(plane?.route_hint, revealedAnswer);
  // Only offer planes the server accepts (it derives `eligible` from the same rule)
  const canSelectPlane =
    isHost && status === 'connected' && !isRoundActive && !isUsed && route.eligible;
  const canStartRound = isHost && status === 'connected' && isSelected && !isRoundActive;
  const canGuess = status === 'connected' && isRoundActive && !hasGuessed;

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

  // The server recorded nothing for a refused guess, so the player can fix it and send again
  useEffect(() => {
    if (!guessRejection) return;
    setHasGuessed(false);
    setGuessError(guessRejection.message);
  }, [guessRejection]);

  // Start the round only once the server confirms the selection. A refused selection then
  // shows one error, not a second one from a startRound that was bound to fail too.
  useEffect(() => {
    if (!startWhenSelected || !isSelected) return;
    setStartWhenSelected(false);
    webSocketClient.send({ type: 'startRound', payload: {} });
  }, [startWhenSelected, isSelected]);

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

  const handleStartRound = () => {
    if (!canStartRound) return;

    try {
      webSocketClient.send({ type: 'startRound', payload: {} });
    } catch (err) {
      console.error('Failed to start round:', err);
    }
  };

  // Combined action: select plane and start round in one tap
  const handleSelectAndStart = () => {
    if (!canSelectPlane) return;

    try {
      webSocketClient.send({ type: 'selectPlane', payload: { hex } });
      setStartWhenSelected(true);
    } catch (err) {
      console.error('Failed to select and start round:', err);
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
    const unknownCodeError = guessCodeError(trimmed);
    if (unknownCodeError) {
      setGuessError(unknownCodeError);
      return;
    }

    try {
      setGuessRejection(null);
      webSocketClient.send({ type: 'guess', payload: { airport_code: trimmed } });
      setHasGuessed(true);
      setGuessError(null);
    } catch (err) {
      setGuessError((err as Error).message);
    }
  };

  const formatAltitudeValue = (alt: number) => {
    return Math.round(alt).toLocaleString();
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
    if (altV > LEVEL_FLIGHT_MAX_FPM) return { symbol: '▲', className: 'text-retro-success' };
    if (altV < -LEVEL_FLIGHT_MAX_FPM) return { symbol: '▼', className: 'text-retro-primary' };
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

  const altTrend = altitudeTrend(plane.alt_v);

  // Determine flight status for display
  const getFlightStatus = () => {
    if (isRoundActive) return { label: 'ACTIVE', className: 'text-retro-success' };
    if (isUsed) return { label: 'DEPARTED', className: 'text-retro-text-muted' };
    if (plane.alt_v > LEVEL_FLIGHT_MAX_FPM) return { label: 'CLIMBING', className: 'text-retro-success' };
    if (plane.alt_v < -LEVEL_FLIGHT_MAX_FPM) return { label: 'DESCENDING', className: 'text-retro-primary' };
    return { label: 'CRUISING', className: 'text-retro-text' };
  };

  const flightStatus = getFlightStatus();

  return (
    <div className={containerClass}>
      <div className="p-4">
        <div className="flex justify-between items-center mb-3">
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

        {/* Host Controls - MOVED TO TOP for mobile accessibility */}
        {isHost && (
          <div className="mb-4">
            {isUsed && !isRoundActive ? (
              // Departed state - show disabled button
              <button
                type="button"
                disabled
                className={retroMode
                  ? 'w-full py-3 px-3 font-display uppercase tracking-widest text-sm border-2 border-retro-border bg-retro-panel text-retro-text-muted cursor-not-allowed opacity-70'
                  : 'w-full rounded py-2 px-3 bg-gray-500 text-white cursor-not-allowed'
                }
              >
                {retroMode ? 'DEPARTED' : 'Already Used'}
              </button>
            ) : isSelected && canStartRound ? (
              // Already selected - show BEGIN ROUND button
              <button
                type="button"
                onClick={handleStartRound}
                className={retroMode
                  ? 'w-full py-3 px-3 font-display uppercase tracking-widest text-sm border-0 bg-retro-primary text-retro-panel hover:bg-retro-primary-bright transition-all'
                  : 'w-full rounded bg-green-500 py-2 px-3 text-white hover:bg-green-600'
                }
              >
                {retroMode ? 'BEGIN ROUND' : 'Start Round'}
              </button>
            ) : !isSelected && canSelectPlane ? (
              // Not selected - show combined START ROUND button (select + start in one tap)
              <button
                type="button"
                onClick={handleSelectAndStart}
                className={retroMode
                  ? 'w-full py-3 px-3 font-display uppercase tracking-widest text-sm border-0 bg-retro-primary text-retro-panel hover:bg-retro-primary-bright transition-all'
                  : 'w-full rounded bg-green-500 py-2 px-3 text-white hover:bg-green-600'
                }
              >
                {retroMode ? 'START ROUND WITH THIS FLIGHT' : 'Start Round with This Flight'}
              </button>
            ) : isSelected && !canStartRound ? (
              // Selected but can't start (e.g., round in progress)
              <div className={retroMode ? 'p-2 border border-retro-primary bg-retro-panel-dark text-center' : 'p-2 bg-blue-900 rounded border border-blue-600 text-center'}>
                <p className={retroMode ? 'text-sm font-display text-retro-primary uppercase tracking-wider' : 'text-sm text-blue-200'}>
                  {retroMode ? '✓ FLIGHT SELECTED' : '✓ Selected for round'}
                </p>
              </div>
            ) : null}
          </div>
        )}

        {/* Compact 2-column flight data grid (3 rows) */}
        <div className="space-y-2 text-sm">
          {/* Row 1: ALT | SPEED */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'ALT' : 'Alt'}</span>
              {retroMode ? (
                <p className="flex items-baseline gap-1">
                  <span className={`text-xs ${altTrend.className}`} aria-hidden="true">
                    {altTrend.symbol}
                  </span>
                  <span className={valueClass}>{formatAltitudeValue(plane.alt)}</span>
                </p>
              ) : (
                <p className={valueClass}>{`${formatAltitudeValue(plane.alt)} ft`}</p>
              )}
            </div>
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'SPD' : 'Speed'}</span>
              {retroMode ? (
                <p className={valueClass}>
                  {formatSpeedValue(plane.lat_v, plane.lon_v) ?? '---'}
                </p>
              ) : (
                <p className={valueClass}>{`${formatSpeedValue(plane.lat_v, plane.lon_v) ?? '---'} kts`}</p>
              )}
            </div>
          </div>

          {/* Row 2: ORIGIN | DEST */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'ORIGIN' : 'Origin'}</span>
              <p className={`${valueClass} truncate`}>
                {formatAirportDisplay(route.origin).toUpperCase()}
              </p>
            </div>
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'DEST' : 'Dest'}</span>
              <p className={`${valueClass} truncate`}>
                {formatAirportDisplay(route.destination).toUpperCase()}
              </p>
            </div>
          </div>

          {/* Row 3: STATUS | AIRLINE */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'STATUS' : 'Status'}</span>
              <p className={retroMode ? 'font-display uppercase tracking-wider text-retro-primary' : valueClass}>
                {flightStatus.label}
              </p>
            </div>
            <div>
              <span className={labelClass} style={labelStyle}>{retroMode ? 'AIRLINE' : 'Airline'}</span>
              <p className={`${retroMode ? 'font-display text-retro-primary uppercase tracking-wider text-xs' : 'text-white text-xs'} truncate`}>
                {plane.operator || '---'}
              </p>
            </div>
          </div>
        </div>


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
                  <p role="alert" className={retroMode ? 'text-sm font-display text-retro-accent uppercase tracking-wider' : 'text-sm text-red-400'}>
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

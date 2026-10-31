import type { RouteHint } from '../common/types';
import type { RevealedAnswer } from '../game/gameSlice';

export type RouteStatus = 'DEPARTING' | 'ARRIVING';

/** What the UI may show about a plane's route. A null airport renders as unknown. */
export interface RouteDisplay {
  origin: string | null;
  destination: string | null;
  status: RouteStatus | null;
  eligible: boolean;
}

const NO_ROUTE: RouteDisplay = { origin: null, destination: null, status: null, eligible: false };

/**
 * Derive the route shown for a plane from the server's route hint.
 *
 * The server only ever sends the monitored end (e.g. KBOS). The guessed end stays
 * null unless `revealed` holds a finished round's answer for that same end; an
 * answer for the other end belongs to another leg and is not shown.
 */
export function getRouteDisplay(
  hint: RouteHint | null | undefined,
  revealed: RevealedAnswer | null,
): RouteDisplay {
  if (!hint?.guess_direction) return NO_ROUTE;
  const revealedCode = revealed?.direction === hint.guess_direction ? revealed.code : null;

  if (hint.guess_direction === 'destination') {
    return {
      origin: hint.known_airport,
      destination: revealedCode,
      status: 'DEPARTING',
      eligible: hint.eligible,
    };
  }
  return {
    origin: revealedCode,
    destination: hint.known_airport,
    status: 'ARRIVING',
    eligible: hint.eligible,
  };
}

import { describe, expect, it } from 'vitest';
import { getRouteDisplay } from '../routeDisplay';

describe('getRouteDisplay', () => {
  it('shows a departure from the monitored airport with its destination unknown', () => {
    const hint = { guess_direction: 'destination' as const, known_airport: 'KBOS', eligible: true };

    expect(getRouteDisplay(hint, null)).toEqual({
      origin: 'KBOS',
      destination: null,
      status: 'DEPARTING',
      eligible: true,
    });
  });

  it('shows an arrival at the monitored airport with its origin unknown', () => {
    const hint = { guess_direction: 'origin' as const, known_airport: 'KBOS', eligible: true };

    expect(getRouteDisplay(hint, null)).toEqual({
      origin: null,
      destination: 'KBOS',
      status: 'ARRIVING',
      eligible: true,
    });
  });

  it('fills the guessed end with a revealed answer', () => {
    const hint = { guess_direction: 'destination' as const, known_airport: 'KBOS', eligible: true };
    const revealed = { code: 'KJFK', direction: 'destination' as const };

    expect(getRouteDisplay(hint, revealed)).toMatchObject({ origin: 'KBOS', destination: 'KJFK' });
  });

  it('does not show an answer revealed for the other end of the route', () => {
    const hint = { guess_direction: 'origin' as const, known_airport: 'KBOS', eligible: true };
    const revealed = { code: 'KJFK', direction: 'destination' as const };

    expect(getRouteDisplay(hint, revealed)).toMatchObject({ origin: null, destination: 'KBOS' });
  });

  it('keeps a plane the server would reject ineligible', () => {
    const hint = { guess_direction: 'origin' as const, known_airport: 'KBOS', eligible: false };

    expect(getRouteDisplay(hint, null).eligible).toBe(false);
  });

  it('shows neither end of an overflight and does not offer it', () => {
    const hint = { guess_direction: null, known_airport: null, eligible: false };

    expect(getRouteDisplay(hint, null)).toEqual({
      origin: null,
      destination: null,
      status: null,
      eligible: false,
    });
  });

  it('treats a plane without a hint as an unknown route', () => {
    expect(getRouteDisplay(undefined, null)).toEqual({
      origin: null,
      destination: null,
      status: null,
      eligible: false,
    });
  });
});

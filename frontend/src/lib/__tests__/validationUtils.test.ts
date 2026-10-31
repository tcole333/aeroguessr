import { describe, it, expect, vi } from 'vitest';
import { assertWsMessage } from '../validationUtils';

const validPing = JSON.stringify({ type: 'ping', payload: { seq: 1 } });
const validPong = JSON.stringify({ type: 'pong', payload: { seq: 2 } });
const validJoined = JSON.stringify({ type: 'playerJoined', payload: { nickname: 'Bob' } });
const validError = JSON.stringify({ type: 'error', payload: { code: 'UNKNOWN_ERROR', message: 'oops' } });

describe('assertWsMessage', () => {
  it('parses valid messages', () => {
    expect(assertWsMessage(validPong)?.type).toBe('pong');
    expect(assertWsMessage(validJoined)?.type).toBe('playerJoined');
    expect(assertWsMessage(validError)?.type).toBe('error');
  });

  it('returns null on invalid JSON', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(assertWsMessage('{')).toBeNull();
  });

  it('returns null for invalid payload', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(assertWsMessage(JSON.stringify({ type: 'ping', payload: {} }))).toBeNull();
  });

  it('returns null for unknown type', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(assertWsMessage(validPing)).toEqual({ type: 'ping', payload: { seq: 1 } });
    expect(assertWsMessage(JSON.stringify({ type: 'nope', payload: {} }))).toBeNull();
  });

  it('accepts the stateSync a joining player receives', () => {
    // Recorded from the backend: the frame a second player gets on connecting.
    const stateSync = {
      type: 'stateSync',
      payload: {
        room_meta: {
          mode: 'Distance',
          round_timeout_seconds: 45,
          host_nickname: 'HostHarry',
          is_solo: false,
          created_ts: 1793423651.578976,
          host_disconnected_ts: null,
        },
        players: {
          JoinerJane: { nickname: 'JoinerJane', score: 0, connected: true, last_seen_ts: 1793423651.782563 },
          HostHarry: { nickname: 'HostHarry', score: 0, connected: true, last_seen_ts: 1793423651.7118971 },
        },
      },
      ts: 1793423651798.089,
    };

    expect(assertWsMessage(JSON.stringify(stateSync))).toEqual(stateSync);
  });
});

describe('assertWsMessage against the answer-secret wire contract', () => {
  it('accepts a plane selection confirm that names no airport', () => {
    const confirm = JSON.stringify({
      type: 'planeSelectedConfirm',
      payload: { hex: 'abc123', guess_direction: 'destination' },
    });

    expect(assertWsMessage(confirm)?.payload).toEqual({
      hex: 'abc123',
      guess_direction: 'destination',
    });
  });

  it('keeps the route hint on a delta plane', () => {
    const routeHint = { guess_direction: 'destination', known_airport: 'KBOS', eligible: true };
    const delta = JSON.stringify({
      type: 'delta',
      payload: {
        planes: {
          updated: [
            {
              hex_ident: 'abc123',
              lat: 42.36,
              lon: -71.0,
              alt: 5000,
              lat_v: 0,
              lon_v: 0,
              alt_v: 0,
              last_update_ts: 1,
              trail: [],
              operator: 'United',
              first_seen_ts: 1,
              update_count: 1,
              route_hint: routeHint,
            },
          ],
          removed: [],
        },
      },
    });

    const parsed = assertWsMessage(delta);

    expect(parsed?.type).toBe('delta');
    expect((parsed?.payload as { planes: { updated: unknown[] } }).planes.updated[0]).toMatchObject({
      operator: 'United',
      route_hint: routeHint,
    });
  });

  it('keeps the plane hex on a round result', () => {
    const result = JSON.stringify({
      type: 'roundResult',
      payload: {
        hex: 'abc123',
        results: [
          {
            nickname: 'Me',
            guess: 'JFK',
            correct_code: 'KJFK',
            score_awarded: 100,
            current_total_score: 100,
          },
        ],
      },
    });

    expect(assertWsMessage(result)?.payload).toMatchObject({ hex: 'abc123' });
  });
});

describe('assertWsMessage on nullable fields', () => {
  function roundResult(guess: unknown): string {
    return JSON.stringify({
      type: 'roundResult',
      payload: {
        hex: 'abc123',
        next_host_nickname: null,
        results: [
          {
            nickname: 'Me',
            guess,
            correct_code: 'KJFK',
            score_awarded: 0,
            current_total_score: 0,
            distance_km: null,
          },
        ],
      },
    });
  }

  it("takes null or the field's type, and nothing else", () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(assertWsMessage(roundResult(null))?.payload).toMatchObject({ results: [{ guess: null }] });
    expect(assertWsMessage(roundResult(42))).toBeNull();
  });
});

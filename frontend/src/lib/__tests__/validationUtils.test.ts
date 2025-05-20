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
});

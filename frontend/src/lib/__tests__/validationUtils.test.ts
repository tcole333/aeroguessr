import { describe, it, expect, vi } from 'vitest';
import { assertWsMessage } from '../validationUtils';

const validPing = JSON.stringify({ type: 'ping', payload: { seq: 1 } });
const validPong = JSON.stringify({ type: 'pong', payload: { seq: 2 } });

describe('assertWsMessage', () => {
  it('parses valid messages', () => {
    expect(assertWsMessage(validPing)?.type).toBe('ping');
    expect(assertWsMessage(validPong)?.type).toBe('pong');
  });

  it('returns null on invalid JSON', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(assertWsMessage('{')).toBeNull();
  });

  it('returns null for invalid payload', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(assertWsMessage(JSON.stringify({ type: 'ping', payload: {} }))).toBeNull();
  });
});

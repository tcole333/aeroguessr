import { createRoomAPI, joinRoomAPI, resolveApiBaseUrl } from '../apiService';
import { expect, it, describe, vi } from 'vitest';

describe('apiService', () => {
  it('defaults to a relative API path when no env override is set', () => {
    expect(resolveApiBaseUrl(undefined)).toBe('/api/v0');
  });

  it('uses the configured API base URL when provided', () => {
    expect(resolveApiBaseUrl('https://example.com/api/v0')).toBe(
      'https://example.com/api/v0',
    );
  });

  it('creates room', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ room_code: 'ABCD', ws_url: 'ws://x' }),
    }));
    const resp = await createRoomAPI({ host_nickname: 'A', mode: 'Exact', round_timeout_seconds: 30 });
    expect(resp.room_code).toBe('ABCD');
    (fetch as vi.Mock).mockRestore();
  });

  it('joins room', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ room_code: 'ABCD', ws_url: 'ws://y' }),
    }));
    const resp = await joinRoomAPI('ABCD', { nickname: 'B' });
    expect(resp.ws_url).toBe('ws://y');
    (fetch as vi.Mock).mockRestore();
  });
});

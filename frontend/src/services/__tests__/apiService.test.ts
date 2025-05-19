import { createRoomAPI, joinRoomAPI } from '../apiService';
import { expect, it, describe, vi } from 'vitest';

describe('apiService', () => {
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

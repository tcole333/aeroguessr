import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { fetchClientConfig } from '../apiService';
import { server } from '../../mocks/server';
import { seattleClientConfig } from '../../mocks/clientConfig';

describe('fetchClientConfig', () => {
  it('returns the config the server sends', async () => {
    await expect(fetchClientConfig()).resolves.toEqual(seattleClientConfig);
  });

  it('rejects with the server error detail', async () => {
    server.use(
      http.get('/api/v0/config', () => HttpResponse.json({ detail: 'Bad gateway' }, { status: 502 })),
    );

    await expect(fetchClientConfig()).rejects.toThrow('Bad gateway');
  });

  it('rejects a response that is not a client config', async () => {
    server.use(
      http.get('/api/v0/config', () => HttpResponse.json({ ...seattleClientConfig, center: undefined })),
    );

    await expect(fetchClientConfig()).rejects.toThrow(/center/);
  });
});

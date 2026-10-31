import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { server } from '../../../mocks/server';
import { seattleClientConfig } from '../../../mocks/clientConfig';
import { createRootStore } from '../../../store/createRootStore';

const failOnce = () =>
  server.use(
    http.get('/api/v0/config', () => new HttpResponse(null, { status: 502 }), { once: true }),
  );

describe('loadClientConfig', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps the config the server sends', async () => {
    const store = createRootStore();

    await store.getState().config.loadClientConfig();

    expect(store.getState().config.clientConfig).toEqual(seattleClientConfig);
  });

  it('reports a failure when the server errors', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    failOnce();
    const store = createRootStore();

    await store.getState().config.loadClientConfig();

    expect(store.getState().config.status).toBe('failed');
  });

  it('loads the config when called again after a failure', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    failOnce();
    const store = createRootStore();

    await store.getState().config.loadClientConfig();
    await store.getState().config.loadClientConfig();

    expect(store.getState().config.clientConfig).toEqual(seattleClientConfig);
  });

  it('asks the server once, however often it is called', async () => {
    let requests = 0;
    server.use(
      http.get('/api/v0/config', () => {
        requests += 1;
        return HttpResponse.json(seattleClientConfig);
      }),
    );
    const store = createRootStore();
    const { loadClientConfig } = store.getState().config;

    await Promise.all([loadClientConfig(), loadClientConfig()]);
    await loadClientConfig();

    expect(requests).toBe(1);
  });
});

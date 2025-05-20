import { render } from '@testing-library/react';
import { vi, it, expect, describe } from 'vitest';
import MapView from '../components/MapView';
import { createRootStore, StoreContext } from '../../../store/createRootStore';
import type { PlaneState } from '../../common/types';

function makePlane(id: number): PlaneState {
  return {
    hex_ident: id.toString(16),
    lat: Math.random() * 180 - 90,
    lon: Math.random() * 360 - 180,
    alt: 30000,
    lat_v: 0,
    lon_v: 0,
    alt_v: 0,
    last_update_ts: Date.now(),
    trail: [
      [Math.random() * 180 - 90, Math.random() * 360 - 180, Date.now()],
    ],
  };
}

function makePlanes(count: number): PlaneState[] {
  return Array.from({ length: count }, (_, i) => makePlane(i));
}

describe('Map performance benchmark', () => {
  const bench = process.env.CI ? it : it.skip;

  bench('updates 100 planes under 300ms', async () => {
    const store = createRootStore();
    store.getState().planes.upsertPlanes(makePlanes(100));
    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <StoreContext.Provider value={store}>{children}</StoreContext.Provider>
    );
    render(<MapView />, { wrapper: Wrapper });
    const iterations = 10;
    let total = 0;
    for (let i = 0; i < iterations; i += 1) {
      const start = performance.now();
      store.getState().planes.upsertPlanes(makePlanes(100));
      await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
      total += performance.now() - start;
    }
    const avg = total / iterations;
    // eslint-disable-next-line no-console
    console.log(`Map update avg: ${avg.toFixed(2)}ms`);
    expect(avg).toBeLessThan(300);
  });

  bench('updates 200 planes under 500ms', async () => {
    const store = createRootStore();
    store.getState().planes.upsertPlanes(makePlanes(200));
    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <StoreContext.Provider value={store}>{children}</StoreContext.Provider>
    );
    render(<MapView />, { wrapper: Wrapper });
    const iterations = 5;
    let total = 0;
    for (let i = 0; i < iterations; i += 1) {
      const start = performance.now();
      store.getState().planes.upsertPlanes(makePlanes(200));
      await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
      total += performance.now() - start;
    }
    const avg = total / iterations;
    // eslint-disable-next-line no-console
    console.log(`Map update avg (200 planes): ${avg.toFixed(2)}ms`);
    expect(avg).toBeLessThan(500);
  });

  bench('detects slow marker performance', async () => {
    vi.mock('../components/PlaneMarker', () => {
      return {
        default: () => {
          const now = performance.now();
          while (performance.now() - now < 10) {
            /* busy wait */
          }
          return null;
        },
      };
    });
    const store = createRootStore();
    store.getState().planes.upsertPlanes(makePlanes(50));
    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <StoreContext.Provider value={store}>{children}</StoreContext.Provider>
    );
    render(<MapView />, { wrapper: Wrapper });
    const start = performance.now();
    store.getState().planes.upsertPlanes(makePlanes(50));
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
    const elapsed = performance.now() - start;
    // eslint-disable-next-line no-console
    console.log(`Slow marker elapsed: ${elapsed.toFixed(2)}ms`);
    expect(elapsed).toBeGreaterThan(300);
    vi.clearAllMocks();
  });
});

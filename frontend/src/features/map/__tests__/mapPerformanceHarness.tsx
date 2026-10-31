import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import MapView from '../components/MapView';
import { StoreContext } from '../../../store/createRootStore';
import type { PlaneState } from '../../common/types';
import { createStoreWithClientConfig } from '../../../mocks/configuredStore';

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
    trail: [[Math.random() * 180 - 90, Math.random() * 360 - 180, Date.now()]],
  };
}

export function makePlanes(count: number): PlaneState[] {
  return Array.from({ length: count }, (_, i) => makePlane(i));
}

/**
 * Render MapView with `planeCount` planes, then replace them `iterations` times and return the
 * average milliseconds from each store update to the next animation frame.
 */
export async function averageMapUpdateMs(planeCount: number, iterations: number): Promise<number> {
  const store = await createStoreWithClientConfig();
  store.getState().planes.upsertPlanes(makePlanes(planeCount));
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <StoreContext.Provider value={store}>{children}</StoreContext.Provider>
  );
  render(<MapView />, { wrapper: Wrapper });

  let total = 0;
  for (let i = 0; i < iterations; i += 1) {
    const start = performance.now();
    store.getState().planes.upsertPlanes(makePlanes(planeCount));
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
    total += performance.now() - start;
  }
  return total / iterations;
}

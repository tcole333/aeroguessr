import { it, expect, describe, vi } from 'vitest';
import { averageMapUpdateMs } from './mapPerformanceHarness';

// vi.mock is hoisted to the top of the file, so this slow marker would also slow down every
// other test here. It lives in its own file to keep the budget tests honest.
const SLOW_MARKER_MS = 10;
vi.mock('../components/PlaneMarker', () => ({
  default: () => {
    const start = performance.now();
    while (performance.now() - start < SLOW_MARKER_MS) {
      /* busy wait */
    }
    return null;
  },
}));

describe('Map performance harness', () => {
  it('detects slow marker rendering', async () => {
    // 50 markers x 10ms each cannot re-render in under 300ms, so a passing budget test means
    // the markers really were rendered fast, not skipped.
    expect(await averageMapUpdateMs(50, 1)).toBeGreaterThan(300);
  });
});

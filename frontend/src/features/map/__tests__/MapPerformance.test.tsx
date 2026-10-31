import { it, expect, describe } from 'vitest';
import { averageMapUpdateMs } from './mapPerformanceHarness';

// Wall-clock budgets for re-rendering the map. Typical averages are 20-100ms, so the budgets
// leave a wide margin for slow CI runners. MapPerformance.canary.test.tsx proves the harness
// would notice slow marker rendering.
describe('Map performance budget', () => {
  it('updates 100 planes under 300ms', async () => {
    expect(await averageMapUpdateMs(100, 10)).toBeLessThan(300);
  });

  it('updates 200 planes under 500ms', async () => {
    expect(await averageMapUpdateMs(200, 5)).toBeLessThan(500);
  });
});

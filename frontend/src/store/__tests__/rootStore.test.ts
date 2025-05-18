import { describe, it, expect } from 'vitest';
import { createRootStore } from '../createRootStore';

describe('createRootStore', () => {
  it('creates store with empty slices', () => {
    const store = createRootStore();
    const state = store.getState();
    expect(state).toEqual({ connection: {}, planes: {}, game: {}, ui: {} });
  });
});

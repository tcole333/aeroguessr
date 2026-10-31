import { createRootStore, type RootStore } from '../store/createRootStore';

/** A store whose client config has loaded from the MSW handler, as after app startup. */
export async function createStoreWithClientConfig(): Promise<RootStore> {
  const store = createRootStore();
  await store.getState().config.loadClientConfig();
  return store;
}

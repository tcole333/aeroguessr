import { useContext } from 'react';
import { useStore as useZustandStore } from 'zustand';
import { StoreContext, RootState } from '../store/createRootStore';

export function useStore<T>(selector: (state: RootState) => T): T {
  const store = useContext(StoreContext);
  if (!store) {
    throw new Error('StoreProvider is missing');
  }
  return useZustandStore(store, selector);
}

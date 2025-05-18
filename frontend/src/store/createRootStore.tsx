import { createStore, StoreApi } from 'zustand';
import { devtools } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';
import React, { ReactNode, createContext, useRef } from 'react';

export interface ConnectionSlice {}
export interface PlaneSlice {}
export interface GameSlice {}
export interface UiSlice {}

export interface RootState {
  connection: ConnectionSlice;
  planes: PlaneSlice;
  game: GameSlice;
  ui: UiSlice;
}

export type RootStore = StoreApi<RootState>;

export function createRootStore(): RootStore {
  return createStore<RootState>()(
    devtools(
      immer(() => ({
        connection: {},
        planes: {},
        game: {},
        ui: {},
      }))
    )
  );
}

export const StoreContext = createContext<RootStore | null>(null);

export function StoreProvider({ children }: { children: ReactNode }): JSX.Element {
  const storeRef = useRef<RootStore>();
  if (!storeRef.current) {
    storeRef.current = createRootStore();
  }
  return <StoreContext.Provider value={storeRef.current}>{children}</StoreContext.Provider>;
}

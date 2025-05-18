import { createStore, StoreApi } from "zustand";
import { devtools, persist } from "zustand/middleware";
import { immer } from "zustand/middleware/immer";
import React, { ReactNode, createContext, useRef } from "react";

import type { ConnectionSlice } from "../features/connection/connectionSlice";
import { createConnectionSlice } from "../features/connection/connectionSlice";
import type { PlanesSlice } from "../features/planes/planesSlice";
import { createPlanesSlice } from "../features/planes/planesSlice";
import type { GameSlice } from "../features/game/gameSlice";
import { createGameSlice } from "../features/game/gameSlice";
import type { UiSlice } from "../features/ui/uiSlice";
import { createUiSlice } from "../features/ui/uiSlice";

export interface RootState {
  connection: ConnectionSlice;
  planes: PlanesSlice;
  game: GameSlice;
  ui: UiSlice;
}

export type RootStore = StoreApi<RootState>;

export function createRootStore(): RootStore {
  return createStore<RootState>()(
    devtools(
      persist(
        immer((set, get) => ({
          connection: createConnectionSlice(set, get),
          planes: createPlanesSlice(set, get),
          game: createGameSlice(set, get),
          ui: createUiSlice(set, get),
        })),
        {
          name: "plane-ui",
          version: 1,
          partialize: (state) => ({ ui: state.ui }),
        },
      ),
    ),
  );
}

export const StoreContext = createContext<RootStore | null>(null);

export function StoreProvider({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  const storeRef = useRef<RootStore>();
  if (!storeRef.current) {
    storeRef.current = createRootStore();
  }
  return (
    <StoreContext.Provider value={storeRef.current}>
      {children}
    </StoreContext.Provider>
  );
}

import { createStore, StoreApi } from "zustand";
import { devtools, persist, PersistOptions } from "zustand/middleware";
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

// Define the part of UiSlice that is persisted
type PersistedUiState = Pick<UiSlice, "activePanel" | "darkMode" | "isPanelOpen">;

export function createRootStore(): RootStore {
  const persistOptions: PersistOptions<RootState, { ui: PersistedUiState }> = {
    name: "plane-ui",
    version: 1,
    // Only persist activePanel, darkMode and isPanelOpen from the ui slice
    partialize: (state) => ({
      ui: {
        activePanel: state.ui.activePanel,
        darkMode: state.ui.darkMode,
        isPanelOpen: state.ui.isPanelOpen,
      },
    }),
    // Custom merge: ensure functions from initial state are kept for the ui slice
    merge: (persistedState, currentState) => {
      const typedPersistedState = persistedState as { ui?: PersistedUiState }; // Type assertion
      return {
        ...currentState, // Start with current state (has functions)
        ...typedPersistedState, // Overlay with persisted non-ui state
        ui: {
          ...currentState.ui, // Current ui slice (has functions)
          ...(typedPersistedState.ui || {}), // Overlay with persisted ui state values
        },
      };
    },
  };

  return createStore<RootState>()(
    devtools(
      persist(
        immer((set, get, api) => {
          return {
            connection: createConnectionSlice(set, get, api),
            planes: createPlanesSlice(set, get, api),
            game: createGameSlice(set, get, api),
            ui: createUiSlice(set, get, api), // Directly create ui slice here
          };
        }),
        persistOptions, // Pass the configured options
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

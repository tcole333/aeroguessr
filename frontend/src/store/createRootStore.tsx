import { createStore, StoreApi } from "zustand";
import { devtools, persist, PersistOptions } from "zustand/middleware";
import { immer } from "zustand/middleware/immer";
import { enableMapSet } from "immer";
import { ReactNode, createContext, useRef } from "react";

// Enable Immer MapSet plugin to work with Sets and Maps
enableMapSet();

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

// Define the parts that are persisted
type PersistedUiState = Pick<UiSlice, "activePanel" | "darkMode" | "isPanelOpen" | "currentView">;
type PersistedConnectionState = Pick<ConnectionSlice, "nickname" | "roomCode" | "wsUrl">;

export function createRootStore(): RootStore {
  const persistOptions: PersistOptions<RootState, { ui: PersistedUiState; connection: PersistedConnectionState }> = {
    name: "plane-session",
    version: 2,
    // Persist UI preferences and connection details for rejoin functionality
    partialize: (state) => ({
      ui: {
        activePanel: state.ui.activePanel,
        darkMode: state.ui.darkMode,
        isPanelOpen: state.ui.isPanelOpen,
        currentView: state.ui.currentView,
      },
      connection: {
        nickname: state.connection.nickname,
        roomCode: state.connection.roomCode,
        wsUrl: state.connection.wsUrl,
      },
    }),
    // Custom merge: ensure functions from initial state are kept
    merge: (persistedState, currentState) => {
      const typedPersistedState = persistedState as {
        ui?: PersistedUiState;
        connection?: PersistedConnectionState;
      };
      return {
        ...currentState, // Start with current state (has functions)
        ui: {
          ...currentState.ui, // Current ui slice (has functions)
          ...(typedPersistedState.ui || {}), // Overlay with persisted ui state values
        },
        connection: {
          ...currentState.connection, // Current connection slice (has functions)
          ...(typedPersistedState.connection || {}), // Overlay with persisted connection state values
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

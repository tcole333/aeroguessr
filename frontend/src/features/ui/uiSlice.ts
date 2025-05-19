import type { StateCreator } from "zustand";
import type { RootState } from "../../store/createRootStore";

export type Panel = "planes" | "leaderboard" | "settings";

export interface UiSlice {
  darkMode: boolean;
  activePanel: Panel;
  isPanelOpen: boolean;
  toggleDarkMode: () => void;
  setActivePanel: (panel: Panel) => void;
  togglePanelOpen: () => void;
}

export const createUiSlice: StateCreator<RootState, [], [], UiSlice> = (
  set,
) => ({
  darkMode: false,
  activePanel: "planes",
  isPanelOpen: true,
  toggleDarkMode: () =>
    set((state) => {
      state.ui.darkMode = !state.ui.darkMode;
    }),
  setActivePanel: (panel) =>
    set((state) => {
      state.ui.activePanel = panel;
    }),
  togglePanelOpen: () =>
    set((state) => {
      state.ui.isPanelOpen = !state.ui.isPanelOpen;
    }),
});

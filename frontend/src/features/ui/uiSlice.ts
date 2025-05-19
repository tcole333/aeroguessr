import type { StateCreator } from "zustand";
import type { RootState } from "../../store/createRootStore";

export type Panel = "planes" | "leaderboard" | "settings";

export interface UiSlice {
  darkMode: boolean;
  activePanel: Panel;
  toggleDarkMode: () => void;
  setActivePanel: (panel: Panel) => void;
}

export const createUiSlice: StateCreator<RootState, [], [], UiSlice> = (
  set,
) => ({
  darkMode: false,
  activePanel: "planes",
  toggleDarkMode: () =>
    set((state) => {
      state.ui.darkMode = !state.ui.darkMode;
    }),
  setActivePanel: (panel) =>
    set((state) => {
      state.ui.activePanel = panel;
    }),
});

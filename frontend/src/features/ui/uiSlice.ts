import type { StateCreator } from "zustand";
import type { RootState } from "../../store/createRootStore";

export type Panel = "planes" | "leaderboard" | "settings";

export interface UiSlice {
  darkMode: boolean;
  activePanel: Panel;
  isPanelOpen: boolean;
  currentView: 'home' | 'game';
  isLoading: boolean;
  formError: string | null;
  toggleDarkMode: () => void;
  setActivePanel: (panel: Panel) => void;
  togglePanelOpen: () => void;
  setCurrentView: (view: 'home' | 'game') => void;
  setLoading: (loading: boolean) => void;
  setFormError: (err: string | null) => void;
  clearFormError: () => void;
}

export const createUiSlice: StateCreator<RootState, [], [], UiSlice> = (
  set,
) => ({
  darkMode: false,
  activePanel: "planes",
  isPanelOpen: true,
  currentView: 'home',
  isLoading: false,
  formError: null,
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
  setCurrentView: (view) =>
    set((state) => {
      state.ui.currentView = view;
    }),
  setLoading: (loading) =>
    set((state) => {
      state.ui.isLoading = loading;
    }),
  setFormError: (err) =>
    set((state) => {
      state.ui.formError = err;
    }),
  clearFormError: () =>
    set((state) => {
      state.ui.formError = null;
    }),
});

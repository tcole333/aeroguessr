import type { StateCreator } from "zustand";
import type { RootState } from "../../store/createRootStore";

export type Panel = "planes" | "leaderboard" | "settings";

export interface UiSlice {
  darkMode: boolean;
  retroMode: boolean;
  activePanel: Panel;
  isPanelOpen: boolean;
  currentView: 'home' | 'game';
  isLoading: boolean;
  formError: string | null;
  expandedPlaneHex: string | null;
  toggleDarkMode: () => void;
  toggleRetroMode: () => void;
  setActivePanel: (panel: Panel) => void;
  togglePanelOpen: () => void;
  setCurrentView: (view: 'home' | 'game') => void;
  setLoading: (loading: boolean) => void;
  setFormError: (err: string | null) => void;
  clearFormError: () => void;
  setExpandedPlane: (hex: string | null) => void;
}

export const createUiSlice: StateCreator<
  RootState,
  [["zustand/immer", never]],
  [],
  UiSlice
> = (set) => ({
  darkMode: false,
  retroMode: true,
  activePanel: "planes",
  isPanelOpen: true,
  currentView: 'home',
  isLoading: false,
  formError: null,
  expandedPlaneHex: null,
  toggleDarkMode: () =>
    set((state) => {
      state.ui.darkMode = !state.ui.darkMode;
    }),
  toggleRetroMode: () =>
    set((state) => {
      state.ui.retroMode = !state.ui.retroMode;
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
      if (view === 'game') {
        state.ui.activePanel = 'planes';
        state.ui.isPanelOpen = true;
      }
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
  setExpandedPlane: (hex) =>
    set((state) => {
      state.ui.expandedPlaneHex = hex;
      // Switch to planes panel when expanding a plane
      if (hex !== null) {
        state.ui.activePanel = 'planes';
        state.ui.isPanelOpen = true;
      }
    }),
});

import type { RootState } from "../../store/createRootStore";

export const selectDarkMode = (state: RootState) => state.ui.darkMode;
export const selectActivePanel = (state: RootState) => state.ui.activePanel;
export const selectIsPanelOpen = (state: RootState) => state.ui.isPanelOpen;
export const selectCurrentView = (state: RootState) => state.ui.currentView;
export const selectIsLoading = (state: RootState) => state.ui.isLoading;
export const selectFormError = (state: RootState) => state.ui.formError;
export const selectExpandedPlane = (state: RootState) => state.ui.expandedPlaneHex;

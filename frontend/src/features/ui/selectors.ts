import type { RootState } from "../../store/createRootStore";

export const selectDarkMode = (state: RootState) => state.ui.darkMode;
export const selectActivePanel = (state: RootState) => state.ui.activePanel;

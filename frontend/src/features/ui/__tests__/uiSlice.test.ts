import { describe, it, expect } from "vitest";
import { createRootStore } from "../../../store/createRootStore";

describe("uiSlice", () => {
  it("toggles dark mode and persists", () => {
    const store = createRootStore();
    store.getState().ui.toggleDarkMode();
    expect(store.getState().ui.darkMode).toBe(true);
    const persisted = localStorage.getItem("plane-ui");
    expect(persisted).toMatch(/"darkMode":true/);
  });

  it("toggles panel open state and persists", () => {
    const store = createRootStore();
    expect(store.getState().ui.isPanelOpen).toBe(true);
    store.getState().ui.togglePanelOpen();
    expect(store.getState().ui.isPanelOpen).toBe(false);
    const persisted = localStorage.getItem("plane-ui");
    expect(persisted).toMatch(/"isPanelOpen":false/);
  });

  it("updates loading, error and view state", () => {
    const store = createRootStore();
    store.getState().ui.setLoading(true);
    store.getState().ui.setFormError("oops");
    store.getState().ui.setCurrentView("game");
    expect(store.getState().ui.isLoading).toBe(true);
    expect(store.getState().ui.formError).toBe("oops");
    expect(store.getState().ui.currentView).toBe("game");
    store.getState().ui.clearFormError();
    expect(store.getState().ui.formError).toBeNull();
  });
});

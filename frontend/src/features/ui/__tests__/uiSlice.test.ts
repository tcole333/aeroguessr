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
});

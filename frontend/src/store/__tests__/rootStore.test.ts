import { describe, it, expect } from "vitest";
import { createRootStore } from "../createRootStore";

describe("createRootStore", () => {
  it("creates store with initial slice state", () => {
    const store = createRootStore();
    const state = store.getState();
    expect(state.connection.status).toBe("disconnected");
    expect(state.connection.error).toBeNull();
    expect(state.connection.nickname).toBeNull();
    expect(state.planes.values).toEqual({});
    expect(state.game.players).toEqual({});
    expect(state.ui.darkMode).toBe(false);
  });
});

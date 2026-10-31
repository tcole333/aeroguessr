import { describe, it, expect } from "vitest";
import { createRootStore } from "../../../store/createRootStore";

describe("connectionSlice", () => {
  it("updates status and error", () => {
    const store = createRootStore();
    store.getState().connection.setStatus("connected");
    store.getState().connection.setError("boom");
    const state = store.getState();
    expect(state.connection.status).toBe("connected");
    expect(state.connection.error).toBe("boom");
    store.getState().connection.setError(null);
    expect(store.getState().connection.error).toBeNull();
  });

  it("sets and clears connection details", () => {
    const store = createRootStore();
    store.getState().connection.setConnectionDetails({
      roomCode: 'ABCD',
      wsUrl: 'ws://x',
      nickname: 'Nick',
    });
    expect(store.getState().connection.roomCode).toBe('ABCD');
    store.getState().connection.clearConnectionDetails();
    expect(store.getState().connection.wsUrl).toBeNull();
  });
});

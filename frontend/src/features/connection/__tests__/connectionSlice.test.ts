import { describe, it, expect } from "vitest";
import { createRootStore } from "../../../store/createRootStore";

describe("connectionSlice", () => {
  it("updates status and latency", () => {
    const store = createRootStore();
    store.getState().connection.setStatus("connected");
    store.getState().connection.updateLatency(123);
    store.getState().connection.setLastHeartbeat(456);
    store.getState().connection.setNickname("Me");
    const state = store.getState();
    expect(state.connection.status).toBe("connected");
    expect(state.connection.latencyMs).toBe(123);
    expect(state.connection.lastHeartbeat).toBe(456);
    expect(state.connection.nickname).toBe("Me");
    store.getState().connection.setNickname(null);
    expect(store.getState().connection.nickname).toBeNull();
  });
});

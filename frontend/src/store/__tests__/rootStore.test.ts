import { afterEach, describe, it, expect, vi } from "vitest";
import { createRootStore } from "../createRootStore";

describe("createRootStore", () => {
  it("creates store with initial slice state", () => {
    const store = createRootStore();
    const state = store.getState();
    expect(state.connection.status).toBe("disconnected");
    expect(state.connection.error).toBeNull();
    expect(state.connection.nickname).toBeNull();
    expect(state.planes.values).toEqual({});
    expect(state.game.scores).toEqual({});
    expect(state.ui.darkMode).toBe(false);
  });

  describe("Redux devtools", () => {
    type DevtoolsWindow = { __REDUX_DEVTOOLS_EXTENSION__?: unknown };

    function installDevtoolsExtension() {
      const connect = vi.fn(() => ({
        init: vi.fn(),
        send: vi.fn(),
        subscribe: vi.fn(() => () => {}),
        unsubscribe: vi.fn(),
      }));
      (window as unknown as DevtoolsWindow).__REDUX_DEVTOOLS_EXTENSION__ = { connect };
      return connect;
    }

    afterEach(() => {
      vi.unstubAllEnvs();
      delete (window as unknown as DevtoolsWindow).__REDUX_DEVTOOLS_EXTENSION__;
    });

    it("does not connect to the extension in a production build", () => {
      const connect = installDevtoolsExtension();
      vi.stubEnv("DEV", false);

      createRootStore();

      expect(connect).not.toHaveBeenCalled();
    });

    it("connects to the extension in development", () => {
      const connect = installDevtoolsExtension();
      vi.stubEnv("DEV", true);

      createRootStore();

      expect(connect).toHaveBeenCalledTimes(1);
    });
  });
});

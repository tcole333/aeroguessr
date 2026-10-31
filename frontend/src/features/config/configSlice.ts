import type { StateCreator } from "zustand";
import type { RootState } from "../../store/createRootStore";
import { fetchClientConfig, type ClientConfig } from "../../services/apiService";

export type ClientConfigStatus = "idle" | "loading" | "ready" | "failed";

/** The server's client config: where this install is and how to draw its map. */
export interface ConfigSlice {
  status: ClientConfigStatus;
  clientConfig: ClientConfig | null;
  /** Fetches the config unless it is loaded or loading; after a failure, retries. */
  loadClientConfig: () => Promise<void>;
}

export const createConfigSlice: StateCreator<
  RootState,
  [["zustand/immer", never]],
  [],
  ConfigSlice
> = (set, get) => ({
  status: "idle",
  clientConfig: null,
  loadClientConfig: async () => {
    const { status } = get().config;
    if (status === "loading" || status === "ready") return;
    set((state) => {
      state.config.status = "loading";
    });
    try {
      const clientConfig = await fetchClientConfig();
      set((state) => {
        state.config.status = "ready";
        state.config.clientConfig = clientConfig;
      });
    } catch (error) {
      console.warn("[config] Failed to load the client config", String(error));
      set((state) => {
        state.config.status = "failed";
      });
    }
  },
});

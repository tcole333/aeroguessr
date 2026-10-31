import type { RootState } from "../../store/createRootStore";

export const selectClientConfigStatus = (state: RootState) => state.config.status;
export const selectClientConfig = (state: RootState) => state.config.clientConfig;
export const selectLoadClientConfig = (state: RootState) => state.config.loadClientConfig;
export const selectServerVersion = (state: RootState) => state.config.clientConfig?.version ?? null;

import type { RootState } from "../../store/createRootStore";

export const selectConnectionStatus = (state: RootState) =>
  state.connection.status;
export const selectLatencyMs = (state: RootState) => state.connection.latencyMs;
export const selectLastHeartbeat = (state: RootState) =>
  state.connection.lastHeartbeat;

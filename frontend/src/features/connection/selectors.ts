import type { RootState } from "../../store/createRootStore";

export const selectConnectionStatus = (state: RootState) =>
  state.connection.status;
export const selectLatencyMs = (state: RootState) => state.connection.latencyMs;
export const selectLastHeartbeat = (state: RootState) =>
  state.connection.lastHeartbeat;
export const selectNickname = (state: RootState) => state.connection.nickname;
export const selectRoomCode = (state: RootState) => state.connection.roomCode;
export const selectWsUrl = (state: RootState) => state.connection.wsUrl;
export const selectPlayerNickname = (state: RootState) =>
  state.connection.playerNickname;
export const selectConnectionError = (state: RootState) => state.connection.error;
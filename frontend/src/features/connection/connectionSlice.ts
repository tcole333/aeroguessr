import type { StateCreator } from "zustand";
import type { RootState } from "../../store/createRootStore";
import type { ConnectionStatus } from "../common/types";

export interface ConnectionSlice {
  status: ConnectionStatus;
  latencyMs: number | null;
  lastHeartbeat: number | null;
  nickname: string | null;
  roomCode: string | null;
  wsUrl: string | null;
  playerNickname: string | null;
  setStatus: (status: ConnectionStatus) => void;
  updateLatency: (latency: number) => void;
  setLastHeartbeat: (ts: number | null) => void;
  setNickname: (nickname: string | null) => void;
  setConnectionDetails: (d: { roomCode: string; wsUrl: string; nickname: string }) => void;
  clearConnectionDetails: () => void;
}

export const createConnectionSlice: StateCreator<
  RootState,
  [["zustand/immer", never]],
  [],
  ConnectionSlice
> = (set) => ({
  status: "disconnected",
  latencyMs: null,
  lastHeartbeat: null,
  nickname: null,
  roomCode: null,
  wsUrl: null,
  playerNickname: null,
  setStatus: (status) =>
    set((state) => {
      state.connection.status = status;
    }),
  updateLatency: (latency) =>
    set((state) => {
      state.connection.latencyMs = latency;
    }),
  setLastHeartbeat: (ts) =>
    set((state) => {
      state.connection.lastHeartbeat = ts;
    }),
  setNickname: (nickname) =>
    set((state) => {
      state.connection.nickname = nickname;
    }),
  setConnectionDetails: ({ roomCode, wsUrl, nickname }) =>
    set((state) => {
      state.connection.roomCode = roomCode;
      state.connection.wsUrl = wsUrl;
      state.connection.playerNickname = nickname;
    }),
  clearConnectionDetails: () =>
    set((state) => {
      state.connection.roomCode = null;
      state.connection.wsUrl = null;
      state.connection.playerNickname = null;
    }),
});

import type { StateCreator } from "zustand";
import type { RootState } from "../../store/createRootStore";
import type { ConnectionStatus } from "../common/types";

export interface ConnectionSlice {
  status: ConnectionStatus;
  latencyMs: number | null;
  lastHeartbeat: number | null;
  nickname: string | null;
  setStatus: (status: ConnectionStatus) => void;
  updateLatency: (latency: number) => void;
  setLastHeartbeat: (ts: number | null) => void;
  setNickname: (nickname: string | null) => void;
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
});

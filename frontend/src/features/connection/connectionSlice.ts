import type { StateCreator } from "zustand";
import type { RootState } from "../../store/createRootStore";
import type { ConnectionStatus } from "../common/types";

export interface ConnectionSlice {
  status: ConnectionStatus;
  nickname: string | null;
  roomCode: string | null;
  wsUrl: string | null;
  error: string | null;
  isRejoinAttempt: boolean;
  setStatus: (status: ConnectionStatus) => void;
  setError: (err: string | null) => void;
  setConnectionDetails: (d: { roomCode: string; wsUrl: string; nickname: string }) => void;
  clearConnectionDetails: () => void;
  setIsRejoinAttempt: (isRejoin: boolean) => void;
}

export const createConnectionSlice: StateCreator<
  RootState,
  [["zustand/immer", never]],
  [],
  ConnectionSlice
> = (set) => ({
  status: "disconnected",
  nickname: null,
  roomCode: null,
  wsUrl: null,
  error: null,
  isRejoinAttempt: false,
  setStatus: (status) =>
    set((state) => {
      state.connection.status = status;
    }),
  setError: (err) =>
    set((state) => {
      state.connection.error = err;
    }),
  setConnectionDetails: ({ roomCode, wsUrl, nickname }) =>
    set((state) => {
      state.connection.roomCode = roomCode;
      state.connection.wsUrl = wsUrl;
      state.connection.nickname = nickname;
    }),
  clearConnectionDetails: () =>
    set((state) => {
      state.connection.roomCode = null;
      state.connection.wsUrl = null;
      state.connection.nickname = null;
      state.connection.isRejoinAttempt = false;
    }),
  setIsRejoinAttempt: (isRejoin) =>
    set((state) => {
      state.connection.isRejoinAttempt = isRejoin;
    }),
});

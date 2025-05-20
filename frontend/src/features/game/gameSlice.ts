import type { StateCreator } from "zustand";
import type { RootState } from "../../store/createRootStore";
import type {
  DeltaPayload,
  FullRoomState,
  RoundResultPayload,
  RoundStartPayload,
  RoundDelta,
} from "../common/types";

export interface RoundInfo extends RoundDelta {
  hex?: string;
  direction?: string;
}

export interface GameSlice {
  roomCode: string | null;
  players: Record<string, unknown>;
  scores: Record<string, number>;
  hostNickname: string | null;
  isSolo: boolean;
  round: RoundInfo | null;
  roundTimeout: number | null;
  selectedPlaneHex: string | null;
  hydrate: (state: FullRoomState) => void;
  applyDelta: (delta: DeltaPayload) => void;
  setRoundStart: (payload: RoundStartPayload) => void;
  setRoundResult: (payload: RoundResultPayload) => void;
  setSelectedPlane: (hex: string | null) => void;
  setHostNickname: (nick: string | null) => void;
  leaveRoom: () => void;
}

const initialState: Omit<
  GameSlice,
  "hydrate" | "applyDelta" | "setRoundStart" | "setRoundResult" | "setHostNickname" | "leaveRoom"
> = {
  roomCode: null,
  players: {},
  scores: {},
  hostNickname: null,
  isSolo: false,
  round: null,
  roundTimeout: null,
  selectedPlaneHex: null,
};

export const createGameSlice: StateCreator<
  RootState,
  [["zustand/immer", never]],
  [],
  GameSlice
> = (set) => ({
  ...initialState,
  hydrate: (stateSync) =>
    set((state) => {
      state.game.players = stateSync.players;
      state.game.scores = {};
      Object.entries(stateSync.players).forEach(([nick, data]) => {
        if (typeof data === 'object' && data && 'score' in data) {
          state.game.scores[nick] = (data as any).score as number;
        }
      });
      if (stateSync.room_meta) {
        state.game.roomCode = (stateSync.room_meta.code as string) || null;
        state.game.hostNickname =
          (stateSync.room_meta.host_nickname as string) || null;
        state.game.isSolo = Boolean(stateSync.room_meta.is_solo);
        state.game.roundTimeout =
          (stateSync.room_meta.round_timeout_seconds as number) || null;
      }
    }),
  applyDelta: (delta) =>
    set((state) => {
      if (delta.scores) {
        Object.entries(delta.scores).forEach(([nick, score]) => {
          state.game.scores[nick] = score;
        });
      }
      if (delta.round) {
        state.game.round = { ...delta.round };
      }
    }),
  setRoundStart: (payload) =>
    set((state) => {
      state.game.round = {
        state: "guessing",
        round_number: payload.round_number,
        hex: payload.hex,
        direction: payload.direction,
      };
      state.game.roundTimeout = payload.timeout_s;
      state.game.selectedPlaneHex = null;
    }),
  setRoundResult: (payload) =>
    set((state) => {
      payload.results.forEach((r) => {
        state.game.scores[r.nickname] = r.current_total_score;
      });
      if (payload.next_host_nickname) {
        state.game.hostNickname = payload.next_host_nickname;
      }
      state.game.round = null;
      state.game.roundTimeout = null;
    }),
  setSelectedPlane: (hex) =>
    set((state) => {
      state.game.selectedPlaneHex = hex;
    }),
  setHostNickname: (nick) =>
    set((state) => {
      state.game.hostNickname = nick;
    }),
  leaveRoom: () =>
    set((state) => {
      Object.assign(state.game, initialState);
      state.connection.nickname = null;
    }),
});

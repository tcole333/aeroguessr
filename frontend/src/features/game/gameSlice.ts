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
  hydrate: (state: FullRoomState) => void;
  applyDelta: (delta: DeltaPayload) => void;
  setRoundStart: (payload: RoundStartPayload) => void;
  setRoundResult: (payload: RoundResultPayload) => void;
  leaveRoom: () => void;
}

const initialState: Omit<
  GameSlice,
  "hydrate" | "applyDelta" | "setRoundStart" | "setRoundResult" | "leaveRoom"
> = {
  roomCode: null,
  players: {},
  scores: {},
  hostNickname: null,
  isSolo: false,
  round: null,
  roundTimeout: null,
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
  leaveRoom: () =>
    set((state) => {
      Object.assign(state.game, initialState);
      state.connection.nickname = null;
    }),
});

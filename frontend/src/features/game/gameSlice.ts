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
  guessDirection: string | null;
  usedPlaneHexes: Set<string>;
  hydrate: (state: FullRoomState) => void;
  applyDelta: (delta: DeltaPayload) => void;
  setRoundStart: (payload: RoundStartPayload) => void;
  setRoundResult: (payload: RoundResultPayload) => void;
  setSelectedPlane: (hex: string | null) => void;
  setGuessDirection: (direction: string | null) => void;
  setHostNickname: (nickname: string | null) => void;
  leaveRoom: () => void;
}

const initialState: Omit<
  GameSlice,
  "hydrate" | "applyDelta" | "setRoundStart" | "setRoundResult" | "setSelectedPlane" | "setGuessDirection" | "setHostNickname" | "leaveRoom"
> = {
  roomCode: null,
  players: {},
  scores: {},
  hostNickname: null,
  isSolo: false,
  round: null,
  roundTimeout: null,
  selectedPlaneHex: null,
  guessDirection: null,
  usedPlaneHexes: new Set(),
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
      Object.entries(stateSync.players).forEach(([nickname, data]) => {
        if (typeof data === 'object' && data && 'score' in data) {
          state.game.scores[nickname] = (data as any).score as number;
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
        Object.entries(delta.scores).forEach(([nickname, score]) => {
          state.game.scores[nickname] = score;
        });
      }
      if (delta.round) {
        // Only update round if we're not in an active guessing state
        // This prevents delta messages from overriding the round during active gameplay
        if (state.game.round?.state !== 'guessing') {
          state.game.round = { ...delta.round };
        }
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
      // Mark this plane as used - need to create new Set for Immer
      state.game.usedPlaneHexes = new Set([...state.game.usedPlaneHexes, payload.hex]);
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
      // Clear guess direction when plane is deselected
      if (!hex) {
        state.game.guessDirection = null;
      }
    }),
  setGuessDirection: (direction) =>
    set((state) => {
      state.game.guessDirection = direction;
    }),
  setHostNickname: (nickname) =>
    set((state) => {
      state.game.hostNickname = nickname;
    }),
  leaveRoom: () =>
    set((state) => {
      Object.assign(state.game, initialState);
      state.connection.nickname = null;
    }),
});

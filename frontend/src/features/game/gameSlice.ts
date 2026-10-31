import type { StateCreator } from "zustand";
import type { RootState } from "../../store/createRootStore";
import type {
  DeltaPayload,
  FullRoomState,
  GuessDirection,
  RoundResultPayload,
  RoundStartPayload,
  RoundDelta,
} from "../common/types";

export interface RoundInfo extends RoundDelta {
  hex?: string;
  direction?: string;
}

/** A finished round's answer and the end of the plane's route it belongs to. */
export interface RevealedAnswer {
  code: string;
  direction: GuessDirection;
}

/** The server's refusal of this player's latest guess, which it did not record. */
export interface GuessRejection {
  message: string;
}

export interface GameSlice {
  scores: Record<string, number>;
  hostNickname: string | null;
  isSolo: boolean;
  round: RoundInfo | null;
  roundTimeout: number | null;
  selectedPlaneHex: string | null;
  usedPlaneHexes: Set<string>;
  scoringMode: 'Exact' | 'Distance' | null;
  lastRoundResult: RoundResultPayload | null;
  /** Answers revealed by roundResult, keyed by plane hex; the server sends them nowhere else. */
  revealedAnswers: Record<string, RevealedAnswer>;
  /** Set when the server refuses a guess (e.g. an unknown airport code); the guess forms show it. */
  guessRejection: GuessRejection | null;
  hydrate: (state: FullRoomState) => void;
  applyDelta: (delta: DeltaPayload) => void;
  setRoundStart: (payload: RoundStartPayload) => void;
  setRoundResult: (payload: RoundResultPayload) => void;
  setSelectedPlane: (hex: string | null) => void;
  setHostNickname: (nickname: string | null) => void;
  setGuessRejection: (message: string | null) => void;
  addPlayer: (nickname: string) => void;
  removePlayer: (nickname: string) => void;
  leaveRoom: () => void;
}

const initialState: Omit<
  GameSlice,
  "hydrate" | "applyDelta" | "setRoundStart" | "setRoundResult" | "setSelectedPlane" | "setHostNickname" | "setGuessRejection" | "addPlayer" | "removePlayer" | "leaveRoom"
> = {
  scores: {},
  hostNickname: null,
  isSolo: false,
  round: null,
  roundTimeout: null,
  selectedPlaneHex: null,
  usedPlaneHexes: new Set(),
  scoringMode: null,
  lastRoundResult: null,
  revealedAnswers: {},
  guessRejection: null,
};

/**
 * The end of the route a round on `hex` asked for: the round's own direction,
 * else (for a client that joined mid-round) the direction the plane's hint gave.
 */
function roundDirectionFor(state: RootState, hex: string): GuessDirection | null {
  const round = state.game.round;
  const direction =
    round?.hex === hex
      ? round.direction
      : state.planes.values[hex]?.route_hint?.guess_direction;
  return direction === "origin" || direction === "destination" ? direction : null;
}

export const createGameSlice: StateCreator<
  RootState,
  [["zustand/immer", never]],
  [],
  GameSlice
> = (set) => ({
  ...initialState,
  hydrate: (stateSync) =>
    set((state) => {
      state.game.scores = {};
      Object.entries(stateSync.players).forEach(([nickname, data]) => {
        if (typeof data === 'object' && data && 'score' in data) {
          state.game.scores[nickname] = (data as any).score as number;
        }
      });
      if (stateSync.room_meta) {
        state.game.hostNickname =
          (stateSync.room_meta.host_nickname as string) || null;
        state.game.isSolo = Boolean(stateSync.room_meta.is_solo);
        state.game.roundTimeout =
          (stateSync.room_meta.round_timeout_seconds as number) || null;
        state.game.scoringMode = (stateSync.room_meta.mode as 'Exact' | 'Distance') || null;
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
      // A new round on this plane may have a different answer (e.g. its next leg)
      delete state.game.revealedAnswers[payload.hex];
      state.game.guessRejection = null;
    }),
  setRoundResult: (payload) =>
    set((state) => {
      payload.results.forEach((r) => {
        state.game.scores[r.nickname] = r.current_total_score;
      });
      const correctCode = payload.results[0]?.correct_code;
      const direction = payload.hex ? roundDirectionFor(state, payload.hex) : null;
      if (payload.hex && correctCode && direction) {
        state.game.revealedAnswers[payload.hex] = { code: correctCode, direction };
      }
      if (payload.next_host_nickname) {
        state.game.hostNickname = payload.next_host_nickname;
      }
      state.game.round = null;
      state.game.roundTimeout = null;
      state.game.lastRoundResult = payload;
      state.game.guessRejection = null;
    }),
  setSelectedPlane: (hex) =>
    set((state) => {
      state.game.selectedPlaneHex = hex;
    }),
  setHostNickname: (nickname) =>
    set((state) => {
      state.game.hostNickname = nickname;
    }),
  setGuessRejection: (message) =>
    set((state) => {
      // A new object every time, so the forms react even when the same message repeats
      state.game.guessRejection = message === null ? null : { message };
    }),
  addPlayer: (nickname) =>
    set((state) => {
      state.game.scores[nickname] = 0;
    }),
  removePlayer: (nickname) =>
    set((state) => {
      delete state.game.scores[nickname];
    }),
  leaveRoom: () =>
    set((state) => {
      Object.assign(state.game, initialState);
      state.connection.nickname = null;
      state.connection.roomCode = null;
      state.connection.wsUrl = null;
      state.connection.isRejoinAttempt = false;
      state.ui.currentView = 'home';
      // Clear planes when leaving room to prevent accumulation
      state.planes.values = {};
    }),
});

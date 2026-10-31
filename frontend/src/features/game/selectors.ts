import type { RootState } from "../../store/createRootStore";

export const selectScores = (state: RootState) => state.game.scores;
export const selectRound = (state: RootState) => state.game.round;
export const selectHost = (state: RootState) => state.game.hostNickname;
export const selectIsSolo = (state: RootState) => state.game.isSolo;
/**
 * Whether this is a solo room, known from its code before stateSync confirms it, and
 * after a reload restores the code. Solo codes look like solo:ab12cd34, as the backend
 * tests them; a multiplayer code is four letters.
 */
export const selectIsSoloRoom = (state: RootState) =>
  state.game.isSolo || (state.connection.roomCode?.startsWith('solo:') ?? false);
export const selectRoundTimeout = (state: RootState) => state.game.roundTimeout;
export const selectSelectedPlane = (state: RootState) =>
  state.game.selectedPlaneHex;
export const selectUsedPlanes = (state: RootState) => state.game.usedPlaneHexes;
export const selectRevealedAnswer = (hex: string) => (state: RootState) =>
  state.game.revealedAnswers[hex] ?? null;
export const selectGuessRejection = (state: RootState) => state.game.guessRejection;

import type { RootState } from "../../store/createRootStore";

export const selectPlayers = (state: RootState) => state.game.players;
export const selectScores = (state: RootState) => state.game.scores;
export const selectRound = (state: RootState) => state.game.round;
export const selectHost = (state: RootState) => state.game.hostNickname;
export const selectIsSolo = (state: RootState) => state.game.isSolo;
export const selectRoundTimeout = (state: RootState) => state.game.roundTimeout;
export const selectSelectedPlane = (state: RootState) =>
  state.game.selectedPlaneHex;

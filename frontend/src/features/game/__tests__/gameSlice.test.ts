import { describe, it, expect } from "vitest";
import { createRootStore } from "../../../store/createRootStore";
import type {
  FullRoomState,
  DeltaPayload,
  RoundStartPayload,
  RoundResultPayload,
} from "../../common/types";

describe("gameSlice", () => {
  it("hydrates and applies delta", () => {
    const store = createRootStore();
    const sync: FullRoomState = {
      room_meta: { host_nickname: 'Host', is_solo: false, code: 'ABCD' },
      players: { A: { score: 5 } },
    };
    store.getState().game.hydrate(sync);
    expect(store.getState().game.players).toEqual({ A: { score: 5 } });
    expect(store.getState().game.hostNickname).toBe('Host');
    expect(store.getState().game.isSolo).toBe(false);
    expect(store.getState().game.roomCode).toBe('ABCD');

    const delta: DeltaPayload = {
      scores: { A: 10 },
      round: { state: "x", round_number: 1 },
    };
    store.getState().game.applyDelta(delta);
    expect(store.getState().game.scores.A).toBe(10);
    expect(store.getState().game.round?.round_number).toBe(1);
  });

  it("handles round start and result then leave", () => {
    const store = createRootStore();
    const start: RoundStartPayload = {
      hex: "1",
      timeout_s: 30,
      direction: "origin",
      round_number: 1,
    };
    store.getState().game.setRoundStart(start);
    expect(store.getState().game.roundTimeout).toBe(30);

    const result: RoundResultPayload = {
      results: [
        {
          nickname: "A",
          guess: "BOS",
          correct_code: "BOS",
          score_awarded: 100,
          current_total_score: 100,
        },
      ],
      next_host_nickname: null,
    };
    store.getState().game.setRoundResult(result);
    expect(store.getState().game.round).toBeNull();
    expect(store.getState().game.scores.A).toBe(100);

    store.getState().game.setHostNickname('NewHost');
    expect(store.getState().game.hostNickname).toBe('NewHost');

    store.getState().game.setSelectedPlane('abc');
    expect(store.getState().game.selectedPlaneHex).toBe('abc');

    store.getState().connection.setNickname('Me');
    store.getState().game.leaveRoom();
    expect(store.getState().game.players).toEqual({});
    expect(store.getState().connection.nickname).toBeNull();
  });
});

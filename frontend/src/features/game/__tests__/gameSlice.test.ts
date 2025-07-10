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

  it("handles player join and leave", () => {
    const store = createRootStore();

    // Add first player
    store.getState().game.addPlayer('Player1');
    expect(store.getState().game.players['Player1']).toEqual({
      nickname: 'Player1',
      score: 0,
      connected: true,
      last_seen_ts: expect.any(Number),
    });
    expect(store.getState().game.scores['Player1']).toBe(0);

    // Add second player
    store.getState().game.addPlayer('Player2');
    expect(store.getState().game.players['Player2']).toEqual({
      nickname: 'Player2',
      score: 0,
      connected: true,
      last_seen_ts: expect.any(Number),
    });
    expect(store.getState().game.scores['Player2']).toBe(0);

    // Both players should exist
    expect(Object.keys(store.getState().game.players)).toHaveLength(2);
    expect(Object.keys(store.getState().game.scores)).toHaveLength(2);

    // Remove first player
    store.getState().game.removePlayer('Player1');
    expect(store.getState().game.players['Player1']).toBeUndefined();
    expect(store.getState().game.scores['Player1']).toBeUndefined();

    // Second player should still exist
    expect(store.getState().game.players['Player2']).toBeDefined();
    expect(store.getState().game.scores['Player2']).toBe(0);
    expect(Object.keys(store.getState().game.players)).toHaveLength(1);
  });

  it("handles host updates from newHost message", () => {
    const store = createRootStore();

    // Set initial host
    store.getState().game.setHostNickname('InitialHost');
    expect(store.getState().game.hostNickname).toBe('InitialHost');

    // Update host
    store.getState().game.setHostNickname('NewHost');
    expect(store.getState().game.hostNickname).toBe('NewHost');

    // Clear host
    store.getState().game.setHostNickname(null);
    expect(store.getState().game.hostNickname).toBeNull();
  });
});

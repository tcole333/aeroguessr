import { describe, it, expect } from "vitest";
import { createRootStore } from "../../../store/createRootStore";
import { selectRevealedAnswer } from "../selectors";
import type {
  FullRoomState,
  DeltaPayload,
  PlaneState,
  RoundStartPayload,
  RoundResultPayload,
} from "../../common/types";

describe("gameSlice", () => {
  it("hydrates and applies delta", () => {
    const store = createRootStore();
    const sync: FullRoomState = {
      room_meta: { host_nickname: 'Host', is_solo: false },
      players: { A: { score: 5 } },
    };
    store.getState().game.hydrate(sync);
    expect(store.getState().game.scores).toEqual({ A: 5 });
    expect(store.getState().game.hostNickname).toBe('Host');
    expect(store.getState().game.isSolo).toBe(false);

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

    store.getState().connection.setConnectionDetails({ roomCode: 'ABCD', wsUrl: 'ws://x', nickname: 'Me' });
    store.getState().game.leaveRoom();
    expect(store.getState().game.scores).toEqual({});
    expect(store.getState().connection.nickname).toBeNull();
  });

  it("handles player join and leave", () => {
    const store = createRootStore();

    store.getState().game.addPlayer('Player1');
    store.getState().game.addPlayer('Player2');
    expect(store.getState().game.scores).toEqual({ Player1: 0, Player2: 0 });

    store.getState().game.removePlayer('Player1');
    expect(store.getState().game.scores).toEqual({ Player2: 0 });
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

  describe("revealed answers", () => {
    const roundStart: RoundStartPayload = {
      hex: "abc",
      timeout_s: 30,
      direction: "destination",
      round_number: 1,
    };
    const resultFor = (hex?: string): RoundResultPayload => ({
      hex,
      results: [
        {
          nickname: "A",
          guess: "JFK",
          correct_code: "KJFK",
          score_awarded: 100,
          current_total_score: 100,
        },
      ],
      next_host_nickname: null,
    });

    const arrivingPlane = (hex: string): PlaneState => ({
      hex_ident: hex,
      lat: 42.36,
      lon: -71.0,
      alt: 5000,
      lat_v: 0,
      lon_v: 0,
      alt_v: 0,
      last_update_ts: 1,
      trail: [],
      route_hint: { guess_direction: "origin", known_airport: "KBOS", eligible: true },
    });

    it("remembers the answer a round result reveals for its plane and round end", () => {
      const store = createRootStore();
      store.getState().game.setRoundStart(roundStart);
      store.getState().game.setRoundResult(resultFor("abc"));

      expect(selectRevealedAnswer("abc")(store.getState())).toEqual({
        code: "KJFK",
        direction: "destination",
      });
    });

    it("takes the round end from the plane's hint for a client that joined mid-round", () => {
      const store = createRootStore();
      store.getState().planes.upsertPlanes([arrivingPlane("abc")]);
      store.getState().game.setRoundResult(resultFor("abc"));

      expect(selectRevealedAnswer("abc")(store.getState())).toEqual({
        code: "KJFK",
        direction: "origin",
      });
    });

    it("reveals nothing when the round end is unknown", () => {
      const store = createRootStore();
      store.getState().game.setRoundResult(resultFor("abc"));

      expect(store.getState().game.revealedAnswers).toEqual({});
    });

    it("reveals nothing for a result that names no plane", () => {
      const store = createRootStore();
      store.getState().game.setRoundResult(resultFor(undefined));

      expect(store.getState().game.revealedAnswers).toEqual({});
    });

    it("forgets a plane's answer when a new round starts on it", () => {
      const store = createRootStore();
      store.getState().game.setRoundStart(roundStart);
      store.getState().game.setRoundResult(resultFor("abc"));
      store.getState().game.setRoundStart(roundStart);

      expect(selectRevealedAnswer("abc")(store.getState())).toBeNull();
    });

    it("forgets a plane's answer when the plane is removed", () => {
      const store = createRootStore();
      store.getState().game.setRoundStart(roundStart);
      store.getState().game.setRoundResult(resultFor("abc"));
      store.getState().planes.removePlanes(["abc"]);

      expect(selectRevealedAnswer("abc")(store.getState())).toBeNull();
    });

    it("forgets every answer on leaving the room", () => {
      const store = createRootStore();
      store.getState().game.setRoundStart(roundStart);
      store.getState().game.setRoundResult(resultFor("abc"));
      store.getState().game.leaveRoom();

      expect(store.getState().game.revealedAnswers).toEqual({});
    });
  });

  describe("guess rejection", () => {
    const roundStart: RoundStartPayload = {
      hex: "abc",
      timeout_s: 30,
      direction: "origin",
      round_number: 1,
    };
    const refusal = "Unknown airport code 'XQX'. Enter an IATA (ORD) or ICAO (KORD) code.";

    it("forgets a refused guess when the next round starts", () => {
      const store = createRootStore();
      store.getState().game.setGuessRejection(refusal);
      store.getState().game.setRoundStart(roundStart);

      expect(store.getState().game.guessRejection).toBeNull();
    });

    it("forgets a refused guess when the round ends", () => {
      const store = createRootStore();
      store.getState().game.setRoundStart(roundStart);
      store.getState().game.setGuessRejection(refusal);
      store.getState().game.setRoundResult({ results: [], next_host_nickname: null });

      expect(store.getState().game.guessRejection).toBeNull();
    });
  });
});

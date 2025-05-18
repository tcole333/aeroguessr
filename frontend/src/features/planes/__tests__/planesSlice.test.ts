import { describe, it, expect } from "vitest";
import { createRootStore } from "../../../store/createRootStore";
import type { PlaneState } from "../../common/types";

describe("planesSlice", () => {
  const samplePlane = (hex: string, trailLen = 1): PlaneState => ({
    hex_ident: hex,
    lat: 0,
    lon: 0,
    alt: 0,
    lat_v: 0,
    lon_v: 0,
    alt_v: 0,
    last_update_ts: 1,
    trail: Array.from(
      { length: trailLen },
      () => [0, 0, 0] as [number, number, number],
    ),
  });

  it("upserts and removes planes", () => {
    const store = createRootStore();
    store.getState().planes.upsertPlanes([samplePlane("a")]);
    expect(Object.keys(store.getState().planes.values)).toHaveLength(1);
    store.getState().planes.removePlanes(["a"]);
    expect(Object.keys(store.getState().planes.values)).toHaveLength(0);
  });

  it("caps trail length at 30", () => {
    const store = createRootStore();
    store.getState().planes.upsertPlanes([samplePlane("b", 35)]);
    expect(store.getState().planes.values["b"].trail.length).toBe(30);
  });
});

import type { StateCreator } from "zustand";
import type { RootState } from "../../store/createRootStore";
import type { PlaneState } from "../common/types";

export interface PlanesSlice {
  values: Record<string, PlaneState>;
  upsertPlanes: (updated: PlaneState[]) => void;
  removePlanes: (hexIds: string[]) => void;
  clear: () => void;
}

function capTrail(
  trail: [number, number, number][],
): [number, number, number][] {
  return trail.slice(-30);
}

export const createPlanesSlice: StateCreator<
  RootState,
  [["zustand/immer", never]],
  [],
  PlanesSlice
> = (set) => ({
  values: {},
  upsertPlanes: (updated) =>
    set((state) => {
      updated.forEach((p) => {
        const plane = { ...p, trail: capTrail(p.trail) };
        state.planes.values[p.hex_ident] = plane;
      });
    }),
  removePlanes: (hexIds) =>
    set((state) => {
      hexIds.forEach((id) => {
        delete state.planes.values[id];
        // A plane seen again may be on another leg, with a different answer
        delete state.game.revealedAnswers[id];
      });
    }),
  clear: () =>
    set((state) => {
      state.planes.values = {};
    }),
});

import type { RootState } from "../../store/createRootStore";

export const selectPlaneMap = (state: RootState) => state.planes.values;
export const selectPlaneById = (hex: string) => (state: RootState) =>
  state.planes.values[hex];

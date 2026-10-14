// The part of the stage a layout lays a bar over (progress, result actions), so a preview can fit around it.
// Provided by StageLayout, read by viewers; 0 outside a stage.
import { createContext, useContext } from "react";

export interface StageInset {
  /** Pixels covered at the bottom. */
  bottom: number;
}

export const StageInsetContext = createContext<StageInset>({ bottom: 0 });

export const useStageInset = () => useContext(StageInsetContext);

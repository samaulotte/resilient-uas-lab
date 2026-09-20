import type { PlannedPath, TelemetrySample } from "@reslab/api-client";

/**
 * Data source of the digital twin.
 *
 * The scene pulls from these getters inside its frame loop instead of receiving props,
 * so a telemetry sample never triggers a React render of the 3D tree. The same
 * interface backs the live stream and the stored-data replay.
 */
export interface TwinFeed {
  getSample: () => TelemetrySample | null;
  getTrail: () => readonly TelemetrySample[];
  /** Changes when the trail was replaced and the path geometry must be rebuilt. */
  getGeneration: () => number;
}

export interface TwinScene {
  feed: TwinFeed;
  plannedPath: PlannedPath | null;
}

/** East-North-Up telemetry to the three.js frame: x east, y up, z south. */
export function toSceneVector(position: { x: number; y: number; z: number }): [number, number, number] {
  return [position.x, position.z, -position.y];
}

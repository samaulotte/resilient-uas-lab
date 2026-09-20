import { beforeEach, describe, expect, it } from "vitest";

import { mergeEvents, mergeSamples, useLiveRun } from "@/stores/live-run";
import type {
  RunDetail,
  RunEvent,
  RunSummary,
  StreamSnapshot,
  TelemetrySample,
} from "@reslab/api-client";

function event(sequence: number, overrides: Partial<RunEvent> = {}): RunEvent {
  return {
    run_id: "run-1",
    sequence,
    kind: "OBSERVED_EFFECT",
    source: "adapter",
    severity: "high",
    event_type: "state_change",
    message: `event ${sequence}`,
    simulation_time: sequence,
    ...overrides,
  };
}

function sample(t: number): TelemetrySample {
  return {
    t,
    source: "mock",
    position: { x: t, y: 0, z: 30 },
    attitude: { roll: 0, pitch: 0, yaw: 0 },
    velocity: { vx: 1, vy: 0, vz: 0 },
    mission: {
      phase: "ENROUTE",
      progress: t / 100,
      waypoint_index: 1,
      waypoints_total: 7,
    },
    flight: { mode: "MISSION", armed: true, control_authority: true, autonomy: "mission" },
    navigation: { source: "gnss", gnss_fix: true, position_error: 0.7 },
    communications: { c2_link: true, telemetry_link: true },
    power: { voltage: 16.5, remaining: 0.9 },
    health: { "flight_control.core": "OPERATIONAL" },
  };
}

const RUN: RunDetail = {
  id: "run-1",
  scenario_name: "compound-degradation",
  scenario_version: "1",
  scenario_hash: "sha256:abc",
  scenario_document: "apiVersion: resilient-uas.dev/v1alpha1",
  adapter: "mock",
  vehicle: "x500",
  label: "",
  state: "RUNNING",
  reason: "",
  seed: 42,
  speed: 1,
  runner_id: "runner-dev",
  result: null,
  hard_gate_result: null,
  resilience_score: null,
  summary: null,
  event_count: 2,
  sample_count: 2,
  last_simulation_time: 2,
  mission_complete: false,
  created_at: "2026-01-01T00:00:00Z",
  started_at: "2026-01-01T00:00:01Z",
  ended_at: null,
  updated_at: "2026-01-01T00:00:02Z",
  planned_path: null,
  provenance: {},
  artifacts: [],
  report_available: false,
};

function snapshot(overrides: Partial<StreamSnapshot> = {}): StreamSnapshot {
  return {
    type: "snapshot",
    server_time: "2026-01-01T00:00:02Z",
    run: RUN,
    events: [event(1), event(2)],
    telemetry: [sample(1), sample(2)],
    ...overrides,
  };
}

describe("mergeEvents", () => {
  it("deduplicates by sequence and keeps the order", () => {
    const merged = mergeEvents([event(1), event(2)], [event(2), event(3)]);
    expect(merged.map((item) => item.sequence)).toEqual([1, 2, 3]);
  });

  it("lets the incoming copy win for the same sequence", () => {
    const merged = mergeEvents([event(1, { message: "stale" })], [event(1, { message: "fresh" })]);
    expect(merged).toHaveLength(1);
    expect(merged[0]?.message).toBe("fresh");
  });

  it("keeps the newest events when the cap is reached", () => {
    const merged = mergeEvents([], [event(1), event(2), event(3)], 2);
    expect(merged.map((item) => item.sequence)).toEqual([2, 3]);
  });

  it("returns the same array when nothing comes in", () => {
    const current = [event(1)];
    expect(mergeEvents(current, [])).toBe(current);
  });
});

describe("mergeSamples", () => {
  it("appends ordered samples", () => {
    const merged = mergeSamples([sample(1)], [sample(2), sample(3)]);
    expect(merged.map((item) => item.t)).toEqual([1, 2, 3]);
  });

  it("deduplicates by simulation time when a batch overlaps", () => {
    const merged = mergeSamples([sample(1), sample(2)], [sample(2), sample(3)]);
    expect(merged.map((item) => item.t)).toEqual([1, 2, 3]);
  });

  it("caps the history from the front", () => {
    const merged = mergeSamples([], [sample(1), sample(2), sample(3)], 2);
    expect(merged.map((item) => item.t)).toEqual([2, 3]);
  });
});

describe("live run store", () => {
  beforeEach(() => {
    useLiveRun.getState().start("run-1");
  });

  it("starts clean for a new run", () => {
    const state = useLiveRun.getState();
    expect(state.runId).toBe("run-1");
    expect(state.events).toHaveLength(0);
    expect(state.samples).toHaveLength(0);
    expect(state.status).toBe("connecting");
    expect(state.finished).toBe(false);
  });

  it("replaces the state with a reconnect snapshot without duplicating events", () => {
    useLiveRun.getState().applySnapshot(snapshot());
    useLiveRun.getState().ingest([event(3)], [sample(3)]);
    expect(useLiveRun.getState().events).toHaveLength(3);

    // A reconnect resends the first events; the client must not double them.
    useLiveRun
      .getState()
      .applySnapshot(snapshot({ events: [event(1), event(2), event(3)], telemetry: [sample(3)] }));
    const state = useLiveRun.getState();
    expect(state.events.map((item) => item.sequence)).toEqual([1, 2, 3]);
    expect(state.samples.map((item) => item.t)).toEqual([3]);
    expect(state.latest?.t).toBe(3);
  });

  it("bumps the generation so the flown path is rebuilt after a snapshot", () => {
    const before = useLiveRun.getState().generation;
    useLiveRun.getState().applySnapshot(snapshot());
    expect(useLiveRun.getState().generation).toBe(before + 1);
  });

  it("tracks the furthest simulation time seen", () => {
    useLiveRun.getState().applySnapshot(snapshot());
    useLiveRun.getState().ingest([event(9, { simulation_time: 9 })], []);
    expect(useLiveRun.getState().simulationTime).toBe(9);
  });

  it("closes the stream and folds the final summary in on completion", () => {
    useLiveRun.getState().applySnapshot(snapshot());
    const summary: RunSummary = {
      ...RUN,
      state: "COMPLETED",
      result: "passed",
      hard_gate_result: "passed",
      resilience_score: 92.2,
      reason: "all hard gates passed",
      ended_at: "2026-01-01T00:02:30Z",
      mission_complete: true,
    };
    useLiveRun
      .getState()
      .applyCompleted({ type: "completed", run: summary, report_available: true });
    const state = useLiveRun.getState();
    expect(state.finished).toBe(true);
    expect(state.status).toBe("closed");
    expect(state.reportAvailable).toBe(true);
    expect(state.run?.state).toBe("COMPLETED");
    expect(state.run?.resilience_score).toBe(92.2);
    // Fields that only exist on the detail are preserved.
    expect(state.run?.scenario_document).toBe(RUN.scenario_document);
  });

  it("replaces the history with a full fetch for a terminal run", () => {
    useLiveRun.getState().applySnapshot(snapshot());
    useLiveRun.getState().replaceHistory({ samples: [sample(0.5), sample(1), sample(1.5)] });
    expect(useLiveRun.getState().samples.map((item) => item.t)).toEqual([0.5, 1, 1.5]);
  });
});

"use client";

import { create } from "zustand";

import type {
  PlannedPath,
  RunDetail,
  RunEvent,
  RunSummary,
  StreamCompleted,
  StreamLifecycle,
  StreamRunFinished,
  StreamSnapshot,
  TelemetrySample,
} from "@reslab/api-client";

/** Connection state of the run WebSocket, surfaced in the status bar. */
export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "live"
  | "stale"
  | "reconnecting"
  | "closed"
  | "error";

export const MAX_EVENTS = 2000;
export const MAX_SAMPLES = 6000;
/** No frame for this long while the run is active means the stream went stale. */
export const STALE_AFTER_MS = 30_000;

/**
 * Merge incoming events into the current list.
 *
 * Events are deduplicated by their monotonic `sequence` so a reconnect snapshot can be
 * applied on top of what the client already has without duplicating rows.
 */
export function mergeEvents(
  current: readonly RunEvent[],
  incoming: readonly RunEvent[],
  cap: number = MAX_EVENTS,
): RunEvent[] {
  if (incoming.length === 0) return current as RunEvent[];
  const bySequence = new Map<number, RunEvent>();
  for (const event of current) bySequence.set(event.sequence, event);
  for (const event of incoming) bySequence.set(event.sequence, event);
  const merged = [...bySequence.values()].sort((a, b) => a.sequence - b.sequence);
  return merged.length > cap ? merged.slice(merged.length - cap) : merged;
}

/** Merge telemetry samples, deduplicated by simulation time and ordered. */
export function mergeSamples(
  current: readonly TelemetrySample[],
  incoming: readonly TelemetrySample[],
  cap: number = MAX_SAMPLES,
): TelemetrySample[] {
  if (incoming.length === 0) return current as TelemetrySample[];
  const last = current.at(-1);
  const appendOnly =
    last !== undefined && incoming.every((sample) => sample.t > (last.t ?? 0));
  const merged = appendOnly
    ? [...current, ...incoming]
    : (() => {
        const byTime = new Map<number, TelemetrySample>();
        for (const sample of current) byTime.set(sample.t, sample);
        for (const sample of incoming) byTime.set(sample.t, sample);
        return [...byTime.values()].sort((a, b) => a.t - b.t);
      })();
  return merged.length > cap ? merged.slice(merged.length - cap) : merged;
}

/** Fields of a run summary that may change while the run is streaming. */
function applySummary(run: RunDetail | null, summary: RunSummary): RunDetail | null {
  if (!run) return run;
  return {
    ...run,
    state: summary.state,
    reason: summary.reason,
    result: summary.result,
    hard_gate_result: summary.hard_gate_result,
    resilience_score: summary.resilience_score,
    summary: summary.summary,
    event_count: summary.event_count,
    sample_count: summary.sample_count,
    last_simulation_time: summary.last_simulation_time,
    mission_complete: summary.mission_complete,
    ended_at: summary.ended_at,
    updated_at: summary.updated_at,
  };
}

export interface LiveRunState {
  runId: string | null;
  /** Incremented whenever the sample history is replaced, so the 3D path rebuilds. */
  generation: number;
  run: RunDetail | null;
  plannedPath: PlannedPath | null;
  events: RunEvent[];
  samples: TelemetrySample[];
  latest: TelemetrySample | null;
  simulationTime: number;
  status: ConnectionStatus;
  lastMessageAt: number | null;
  finished: boolean;
  reportAvailable: boolean;
  error: string | null;
  start: (runId: string) => void;
  stop: () => void;
  setStatus: (status: ConnectionStatus) => void;
  setError: (message: string | null) => void;
  applySnapshot: (message: StreamSnapshot) => void;
  applyLifecycle: (message: StreamLifecycle) => void;
  ingest: (events: readonly RunEvent[], samples: readonly TelemetrySample[]) => void;
  applyRunFinished: (message: StreamRunFinished) => void;
  applyCompleted: (message: StreamCompleted) => void;
  replaceHistory: (history: {
    events?: readonly RunEvent[];
    samples?: readonly TelemetrySample[];
  }) => void;
  touch: () => void;
}

const EMPTY = {
  run: null,
  plannedPath: null,
  events: [] as RunEvent[],
  samples: [] as TelemetrySample[],
  latest: null,
  simulationTime: 0,
  status: "idle" as ConnectionStatus,
  lastMessageAt: null,
  finished: false,
  reportAvailable: false,
  error: null,
};

export const useLiveRun = create<LiveRunState>()((set) => ({
  runId: null,
  generation: 0,
  ...EMPTY,

  start: (runId) =>
    set((state) => ({
      ...EMPTY,
      runId,
      generation: state.generation + 1,
      status: "connecting",
    })),

  stop: () => set({ status: "closed" }),

  setStatus: (status) => set({ status }),

  setError: (error) => set({ error }),

  touch: () => set({ lastMessageAt: Date.now() }),

  applySnapshot: (message) =>
    set((state) => {
      const samples = message.telemetry;
      const latest = samples.at(-1) ?? null;
      return {
        run: message.run,
        plannedPath: message.run.planned_path,
        events: mergeEvents([], message.events),
        samples: mergeSamples([], samples),
        latest,
        simulationTime: Math.max(latest?.t ?? 0, message.run.last_simulation_time),
        generation: state.generation + 1,
        lastMessageAt: Date.now(),
        error: null,
        reportAvailable: message.run.report_available,
      };
    }),

  applyLifecycle: (message) =>
    set((state) => ({
      run: state.run ? { ...state.run, state: message.state, reason: message.reason } : state.run,
      plannedPath: message.planned_path ?? state.plannedPath,
      simulationTime: Math.max(state.simulationTime, message.simulation_time),
      lastMessageAt: Date.now(),
    })),

  ingest: (events, samples) =>
    set((state) => {
      const nextSamples = mergeSamples(state.samples, samples);
      const latest = nextSamples.at(-1) ?? state.latest;
      const nextEvents = mergeEvents(state.events, events);
      const lastEventTime = nextEvents.at(-1)?.simulation_time ?? 0;
      return {
        events: nextEvents,
        samples: nextSamples,
        latest,
        simulationTime: Math.max(state.simulationTime, latest?.t ?? 0, lastEventTime),
        lastMessageAt: Date.now(),
      };
    }),

  applyRunFinished: (message) =>
    set((state) => ({
      finished: true,
      simulationTime: Math.max(state.simulationTime, message.simulation_time),
      lastMessageAt: Date.now(),
    })),

  applyCompleted: (message) =>
    set((state) => ({
      run: applySummary(state.run, message.run),
      finished: true,
      reportAvailable: message.report_available,
      status: "closed",
      lastMessageAt: Date.now(),
    })),

  replaceHistory: ({ events, samples }) =>
    set((state) => {
      const nextSamples = samples ? mergeSamples([], samples) : state.samples;
      const nextEvents = events ? mergeEvents([], events) : state.events;
      const latest = nextSamples.at(-1) ?? state.latest;
      return {
        events: nextEvents,
        samples: nextSamples,
        latest,
        simulationTime: Math.max(
          state.simulationTime,
          latest?.t ?? 0,
          nextEvents.at(-1)?.simulation_time ?? 0,
        ),
        generation: state.generation + 1,
      };
    }),
}));

/** Read the newest telemetry sample without subscribing to React updates. */
export function latestSample(): TelemetrySample | null {
  return useLiveRun.getState().latest;
}

export function connectionLabel(status: ConnectionStatus): string {
  switch (status) {
    case "live":
      return "LIVE";
    case "stale":
      return "STALE";
    case "reconnecting":
      return "RECONNECTING";
    case "connecting":
      return "CONNECTING";
    case "closed":
      return "CLOSED";
    case "error":
      return "DISCONNECTED";
    default:
      return "IDLE";
  }
}

export function connectionTone(status: ConnectionStatus): "ok" | "warn" | "bad" | "dim" {
  switch (status) {
    case "live":
      return "ok";
    case "stale":
    case "reconnecting":
    case "connecting":
      return "warn";
    case "error":
      return "bad";
    default:
      return "dim";
  }
}


/**
 * Typed client for the Resilient UAS Lab API.
 *
 * `schema.d.ts` is generated from `packages/schemas/openapi.json` (`pnpm gen:client`).
 * Everything the frontend needs from the backend goes through the types exported here,
 * so a change in a Pydantic model that is not reflected in the UI fails `tsc`.
 */

import createClient, { type Client, type ClientOptions } from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths };

type Schemas = components["schemas"];

export type SystemInfo = Schemas["SystemInfo"];
export type SystemTopology = Schemas["SystemTopology"];
export type TopologyComponent = Schemas["Component"];
export type TopologyDependency = Schemas["Dependency"];
export type TrustBoundary = Schemas["TrustBoundary"];
export type CatalogEntry = Schemas["CatalogEntryOut"];
export type EffectDescriptor = Schemas["EffectDescriptor"];
export type AdapterInfo = Schemas["AdapterOut"];
export type RunnerInfo = Schemas["RunnerOut"];
export type ScoreProfile = Schemas["ScoreProfile"];

export type ScenarioSummary = Schemas["ScenarioSummary"];
export type ScenarioDetail = Schemas["ScenarioDetail"];
export type ScenarioValidateResponse = Schemas["ScenarioValidateResponse"];
export type ValidationIssue = Schemas["ValidationIssue"];

export type RunSummary = Schemas["RunSummary"];
export type RunDetail = Schemas["RunDetail"];
export type RunListResponse = Schemas["RunListResponse"];
export type RunCreateRequest = Schemas["RunCreateRequest"];
export type ArtifactInfo = Schemas["ArtifactOut"];
export type ReportSummary = Schemas["ReportSummary"];

export type RunEvent = Schemas["RunEvent"];
export type EventsResponse = Schemas["EventsResponse"];
export type TelemetrySample = Schemas["TelemetrySample"];
export type TelemetryResponse = Schemas["TelemetryResponse"];
export type PlannedPath = Schemas["PlannedPath"];
export type Position = Schemas["Position"];

export type MetricsResponse = Schemas["MetricsResponse"];
export type MetricsResult = Schemas["MetricsResult"];
export type ScoreResult = Schemas["ScoreResult"];
export type DimensionScore = Schemas["DimensionScore"];
export type AssertionResult = Schemas["AssertionResult"];
export type RecoveryRecord = Schemas["RecoveryRecord"];
export type PropagationMetrics = Schemas["PropagationMetrics"];

export type CompareResponse = Schemas["CompareResponse"];
export type MetricComparison = Schemas["MetricComparison"];
export type AssertionComparison = Schemas["AssertionComparison"];
export type DimensionComparison = Schemas["DimensionComparison"];

export type ComponentState = Schemas["ComponentState"];
export type RunState = Schemas["RunState"];
export type BenchmarkResult = Schemas["BenchmarkResult"];
export type Severity = Schemas["Severity"];
export type EventKind = Schemas["EventKind"];
export type FlightMode = Schemas["FlightMode"];
export type MissionPhase = Schemas["MissionPhase"];
export type Domain = Schemas["Domain"];
export type Effect = Schemas["Effect"];

/** Messages received on `WS /api/v1/runs/{run_id}/stream`. */
export type StreamSnapshot = Schemas["StreamSnapshot"];
export type StreamCompleted = Schemas["StreamCompleted"];
export type StreamHeartbeat = Schemas["StreamHeartbeat"];

export type StreamLifecycle = Schemas["LifecycleMessage"];
export type StreamEvent = Schemas["EventMessage"];
export type StreamTelemetry = Schemas["TelemetryMessage"];
export type StreamRunFinished = Schemas["RunFinishedMessage"];

export type StreamMessage =
  | StreamSnapshot
  | StreamLifecycle
  | StreamEvent
  | StreamTelemetry
  | StreamRunFinished
  | StreamHeartbeat
  | StreamCompleted;

export type ApiClient = Client<paths>;

export function createApiClient(options: ClientOptions = {}): ApiClient {
  return createClient<paths>({ baseUrl: "", ...options });
}

/** Build the WebSocket URL for a run stream relative to the current origin. */
export function runStreamUrl(runId: string, base: string = ""): string {
  if (base) {
    return `${base.replace(/^http/, "ws").replace(/\/$/, "")}/api/v1/runs/${runId}/stream`;
  }
  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/api/v1/runs/${runId}/stream`;
  }
  return `/api/v1/runs/${runId}/stream`;
}

export const TERMINAL_RUN_STATES: readonly RunState[] = ["COMPLETED", "FAILED", "CANCELLED"];

export function isTerminalRunState(state: RunState): boolean {
  return TERMINAL_RUN_STATES.includes(state);
}

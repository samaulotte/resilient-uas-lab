/**
 * Central semantics of every state vocabulary shown in the UI.
 *
 * Components must never hard-code colours or labels for a state; they look them up
 * here so that "healthy is green, degraded is amber, failed is red" holds everywhere.
 */

import type {
  BenchmarkResult,
  ComponentState,
  Domain,
  EventKind,
  FlightMode,
  RunState,
  Severity,
} from "@reslab/api-client";

export type Tone = "ok" | "warn" | "bad" | "info" | "dim";

export interface StateStyle {
  label: string;
  tone: Tone;
  description: string;
}

export const COMPONENT_STATE: Record<ComponentState, StateStyle> = {
  NOMINAL: { label: "NOMINAL", tone: "ok", description: "Performing within specification" },
  OPERATIONAL: { label: "OPERATIONAL", tone: "ok", description: "Performing its function" },
  DEGRADED: { label: "DEGRADED", tone: "warn", description: "Reduced quality or capacity" },
  UNAVAILABLE: { label: "UNAVAILABLE", tone: "bad", description: "Function not provided" },
  FAILED: { label: "FAILED", tone: "bad", description: "Component failed" },
  RECOVERING: { label: "RECOVERING", tone: "warn", description: "Recovery in progress" },
  RECOVERED: { label: "RECOVERED", tone: "ok", description: "Back to a healthy state" },
  UNKNOWN: { label: "UNKNOWN", tone: "dim", description: "No observation available" },
};

export const HEALTHY_STATES: readonly ComponentState[] = ["NOMINAL", "OPERATIONAL", "RECOVERED"];

export function isHealthy(state: ComponentState | undefined): boolean {
  return state !== undefined && HEALTHY_STATES.includes(state);
}

export const RUN_STATE: Record<RunState, StateStyle> = {
  CREATED: { label: "CREATED", tone: "dim", description: "Run record created" },
  VALIDATING: { label: "VALIDATING", tone: "info", description: "Scenario is being validated" },
  QUEUED: { label: "QUEUED", tone: "info", description: "Waiting for a runner" },
  PREPARING: { label: "PREPARING", tone: "info", description: "Runner is preparing the target" },
  RUNNING: { label: "RUNNING", tone: "ok", description: "Scenario executing" },
  RECOVERING: { label: "RECOVERING", tone: "warn", description: "A component is recovering" },
  COLLECTING: { label: "COLLECTING", tone: "info", description: "Collecting artifacts" },
  ANALYZING: { label: "ANALYZING", tone: "info", description: "Computing metrics and report" },
  COMPLETED: { label: "COMPLETED", tone: "ok", description: "Run finished and analyzed" },
  FAILED: { label: "FAILED", tone: "bad", description: "Run could not complete" },
  CANCELLED: { label: "CANCELLED", tone: "dim", description: "Run cancelled" },
};

export const ACTIVE_RUN_STATES: readonly RunState[] = [
  "QUEUED",
  "PREPARING",
  "RUNNING",
  "RECOVERING",
  "COLLECTING",
  "ANALYZING",
];

export const BENCHMARK_RESULT: Record<BenchmarkResult, StateStyle> = {
  passed: { label: "PASSED", tone: "ok", description: "All hard gates passed" },
  failed: { label: "FAILED", tone: "bad", description: "A hard gate failed" },
  inconclusive: { label: "INCONCLUSIVE", tone: "warn", description: "Run did not complete" },
};

export const SEVERITY: Record<Severity, StateStyle> = {
  info: { label: "INFO", tone: "dim", description: "Informational" },
  low: { label: "LOW", tone: "info", description: "Low severity" },
  medium: { label: "MEDIUM", tone: "warn", description: "Medium severity" },
  high: { label: "HIGH", tone: "warn", description: "High severity" },
  critical: { label: "CRITICAL", tone: "bad", description: "Critical severity" },
};

export const EVENT_KIND: Record<EventKind, StateStyle & { short: string }> = {
  INJECTION_REQUEST: {
    label: "Injection requested",
    short: "REQ",
    tone: "info",
    description: "Scenario asked the adapter to inject an effect",
  },
  INJECTION_APPLIED: {
    label: "Injection applied",
    short: "INJ",
    tone: "info",
    description: "Adapter confirmed the effect is active",
  },
  INJECTION_REJECTED: {
    label: "Injection rejected",
    short: "REJ",
    tone: "bad",
    description: "Adapter could not apply the effect",
  },
  INJECTION_CLEARED: {
    label: "Injection cleared",
    short: "CLR",
    tone: "dim",
    description: "Effect removed",
  },
  OBSERVED_EFFECT: {
    label: "Observed effect",
    short: "OBS",
    tone: "warn",
    description: "Component state change observed in the target",
  },
  SYSTEM_RESPONSE: {
    label: "System response",
    short: "RSP",
    tone: "info",
    description: "Autonomous reaction of the target",
  },
  RECOVERY: {
    label: "Recovery",
    short: "RCV",
    tone: "ok",
    description: "Component returned to a healthy state",
  },
  EXPECTATION_RESULT: {
    label: "Expectation",
    short: "EXP",
    tone: "info",
    description: "Declared expectation checked against observations",
  },
  ASSERTION_RESULT: {
    label: "Assertion",
    short: "AST",
    tone: "info",
    description: "Assertion evaluated",
  },
  MISSION: { label: "Mission", short: "MSN", tone: "dim", description: "Mission progress" },
  LIFECYCLE: { label: "Lifecycle", short: "LCY", tone: "dim", description: "Run lifecycle" },
  LOG: { label: "Log", short: "LOG", tone: "dim", description: "Informational" },
};

export const FLIGHT_MODE: Record<FlightMode, StateStyle> = {
  IDLE: { label: "IDLE", tone: "dim", description: "On ground, disarmed" },
  TAKEOFF: { label: "TAKEOFF", tone: "info", description: "Climbing to mission altitude" },
  MISSION: { label: "MISSION", tone: "ok", description: "Following the mission" },
  HOLD: { label: "HOLD", tone: "warn", description: "Holding position (failsafe)" },
  RTL: { label: "RTL", tone: "warn", description: "Returning to launch" },
  LAND: { label: "LAND", tone: "info", description: "Landing" },
  LANDED: { label: "LANDED", tone: "dim", description: "Landed" },
  UNKNOWN: { label: "UNKNOWN", tone: "bad", description: "Mode unknown" },
};

export const DOMAIN_LABEL: Record<Domain, string> = {
  external: "External",
  communications: "Communications",
  navigation: "Navigation",
  mission_compute: "Mission Compute",
  flight_control: "Flight Control",
  actuation: "Actuation",
  power: "Power",
};

/** Display order of domains from least to most trusted (top to bottom in blast radius). */
export const DOMAIN_ORDER: readonly Domain[] = [
  "external",
  "communications",
  "mission_compute",
  "navigation",
  "flight_control",
  "actuation",
  "power",
];

export const CRITICAL_DOMAINS: readonly Domain[] = ["flight_control", "actuation"];

export const TONE_TEXT: Record<Tone, string> = {
  ok: "text-ok",
  warn: "text-warn",
  bad: "text-bad",
  info: "text-info",
  dim: "text-dim",
};

export const TONE_BG: Record<Tone, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  bad: "bg-bad",
  info: "bg-info",
  dim: "bg-dim",
};

export const TONE_SOFT_BG: Record<Tone, string> = {
  ok: "bg-ok-soft",
  warn: "bg-warn-soft",
  bad: "bg-bad-soft",
  info: "bg-info-soft",
  dim: "bg-dim-soft",
};

export const TONE_HEX: Record<Tone, string> = {
  ok: "#2fbf71",
  warn: "#e0a52a",
  bad: "#e05252",
  info: "#4fb3e8",
  dim: "#5d6b7a",
};

export function componentTone(state: ComponentState | undefined): Tone {
  return state ? COMPONENT_STATE[state].tone : "dim";
}

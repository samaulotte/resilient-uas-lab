/**
 * The scenario YAML document is the authoritative format. This module converts between
 * that document and the flat draft the Scenario Studio edits, without ever losing the
 * parts of a document the form does not expose (consequence profiles, labels, waypoints,
 * adapter configuration, scoring profile).
 */

import { dump, load } from "js-yaml";

import { parseDuration } from "@/lib/duration";
import type { ComponentState, Effect, Severity } from "@reslab/api-client";

export const SCENARIO_API_VERSION = "resilient-uas.dev/v1alpha1";
export const SCENARIO_KIND = "ResilienceScenario";

export type AdapterName = "mock" | "px4-gazebo" | "replay";
export type MissionType = "waypoint" | "hover" | "survey";
export type ParameterKind = "number" | "integer" | "duration" | "ratio";

export interface ParameterDraft {
  name: string;
  value: string;
  kind: ParameterKind;
}

export interface ExpectationDraft {
  subsystem: string;
  state: ComponentState;
  within: string;
  description: string;
}

export interface EventDraft {
  id: string;
  at: string;
  subsystem: string;
  effect: Effect;
  /** Empty string means "until the end of the scenario". */
  duration: string;
  parameters: ParameterDraft[];
  expect: ExpectationDraft[];
  description: string;
}

export interface AssertionDraft {
  expression: string;
  severity: Severity;
  description: string;
}

export interface RecoveryDraft {
  gnssLoss: "dead_reckoning" | "hold" | "land";
  datalinkLoss: "continue" | "hold" | "rtl";
  computeLoss: "hold" | "land" | "rtl";
  holdTimeout: string;
  maxDeadReckoning: string;
}

export interface ScenarioDraft {
  name: string;
  description: string;
  version: string;
  tags: string[];
  adapter: AdapterName;
  vehicle: string;
  missionType: MissionType;
  timeout: string;
  altitude: number;
  cruiseSpeed: number;
  recovery: RecoveryDraft;
  seed: number;
  speed: number;
  telemetryRateHz: number;
  events: EventDraft[];
  assertions: AssertionDraft[];
  /** Parts of the document the form does not edit but must preserve. */
  preserved: {
    labels?: Record<string, unknown>;
    configuration?: Record<string, unknown>;
    waypoints?: unknown[];
    profile?: Record<string, unknown>;
    scoring?: Record<string, unknown>;
  };
}

export const RECOVERY_DEFAULTS: RecoveryDraft = {
  gnssLoss: "dead_reckoning",
  datalinkLoss: "continue",
  computeLoss: "hold",
  holdTimeout: "60s",
  maxDeadReckoning: "90s",
};

export function emptyDraft(): ScenarioDraft {
  return {
    name: "",
    description: "",
    version: "1",
    tags: [],
    adapter: "mock",
    vehicle: "x500",
    missionType: "waypoint",
    timeout: "180s",
    altitude: 30,
    cruiseSpeed: 6,
    recovery: { ...RECOVERY_DEFAULTS },
    seed: 42,
    speed: 1,
    telemetryRateHz: 10,
    events: [],
    assertions: [],
    preserved: {},
  };
}

// ---------------------------------------------------------------- narrowing

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number") return String(value);
  return fallback;
}

function asNumber(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function asOneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === "string" && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : fallback;
}

const COMPONENT_STATES: readonly ComponentState[] = [
  "NOMINAL",
  "OPERATIONAL",
  "DEGRADED",
  "UNAVAILABLE",
  "FAILED",
  "RECOVERING",
  "RECOVERED",
  "UNKNOWN",
];

const SEVERITIES: readonly Severity[] = ["info", "low", "medium", "high", "critical"];

export const EFFECTS: readonly Effect[] = [
  "unavailable",
  "intermittent",
  "degraded",
  "erroneous",
  "stuck",
  "restart",
  "crash",
  "latency",
  "packet_loss",
  "resource_pressure",
  "temporary_disconnect",
];

function parameterDrafts(value: unknown): ParameterDraft[] {
  if (!isRecord(value)) return [];
  return Object.entries(value).map(([name, raw]) => ({
    name,
    value: asString(raw),
    kind: typeof raw === "string" ? "duration" : "number",
  }));
}

function expectationDrafts(value: unknown): ExpectationDraft[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((entry) => ({
    subsystem: asString(entry.subsystem),
    state: asOneOf(entry.state, COMPONENT_STATES, "NOMINAL"),
    within: asString(entry.within, "5s"),
    description: asString(entry.description),
  }));
}

function eventDrafts(value: unknown): EventDraft[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((entry, index) => {
    const inject = isRecord(entry.inject) ? entry.inject : {};
    return {
      id: asString(entry.id, `event-${index + 1}`),
      at: asString(entry.at, "30s"),
      subsystem: asString(inject.subsystem),
      effect: asOneOf(inject.effect, EFFECTS, "unavailable"),
      duration: typeof inject.duration === "string" ? inject.duration : "",
      parameters: parameterDrafts(inject.parameters),
      expect: expectationDrafts(entry.expect),
      description: asString(entry.description),
    };
  });
}

function assertionDrafts(value: unknown): AssertionDraft[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((entry) => ({
    expression: asString(entry.expression),
    severity: asOneOf(entry.severity, SEVERITIES, "medium"),
    description: asString(entry.description),
  }));
}

export class ScenarioParseError extends Error {}

/** Parse a YAML document into a draft. Throws `ScenarioParseError` on malformed YAML. */
export function parseScenarioDocument(text: string): ScenarioDraft {
  let parsed: unknown;
  try {
    parsed = load(text);
  } catch (error) {
    // Keep the first line of the parser message: the rest is a source excerpt.
    const message = error instanceof Error ? error.message : "invalid YAML";
    throw new ScenarioParseError(message.split("\n")[0] ?? "invalid YAML");
  }
  if (!isRecord(parsed)) throw new ScenarioParseError("the document must be a YAML mapping");

  const metadata = isRecord(parsed.metadata) ? parsed.metadata : {};
  const target = isRecord(parsed.target) ? parsed.target : {};
  const mission = isRecord(parsed.mission) ? parsed.mission : {};
  const recovery = isRecord(parsed.recovery) ? parsed.recovery : {};
  const simulation = isRecord(parsed.simulation) ? parsed.simulation : {};

  const base = emptyDraft();
  return {
    name: asString(metadata.name),
    description: asString(metadata.description),
    version: asString(metadata.version, "1"),
    tags: asStringArray(metadata.tags),
    adapter: asOneOf(target.adapter, ["mock", "px4-gazebo", "replay"] as const, "mock"),
    vehicle: asString(target.vehicle, "x500"),
    missionType: asOneOf(mission.type, ["waypoint", "hover", "survey"] as const, "waypoint"),
    timeout: asString(mission.timeout, base.timeout),
    altitude: asNumber(mission.altitude, base.altitude),
    cruiseSpeed: asNumber(mission.cruise_speed, base.cruiseSpeed),
    recovery: {
      gnssLoss: asOneOf(
        recovery.gnss_loss,
        ["dead_reckoning", "hold", "land"] as const,
        RECOVERY_DEFAULTS.gnssLoss,
      ),
      datalinkLoss: asOneOf(
        recovery.datalink_loss,
        ["continue", "hold", "rtl"] as const,
        RECOVERY_DEFAULTS.datalinkLoss,
      ),
      computeLoss: asOneOf(
        recovery.compute_loss,
        ["hold", "land", "rtl"] as const,
        RECOVERY_DEFAULTS.computeLoss,
      ),
      holdTimeout: asString(recovery.hold_timeout, RECOVERY_DEFAULTS.holdTimeout),
      maxDeadReckoning: asString(
        recovery.max_dead_reckoning,
        RECOVERY_DEFAULTS.maxDeadReckoning,
      ),
    },
    seed: asNumber(simulation.seed, base.seed),
    speed: asNumber(simulation.speed, base.speed),
    telemetryRateHz: asNumber(simulation.telemetry_rate_hz, base.telemetryRateHz),
    events: eventDrafts(parsed.events),
    assertions: assertionDrafts(parsed.assertions),
    preserved: {
      ...(isRecord(metadata.labels) && Object.keys(metadata.labels).length > 0
        ? { labels: metadata.labels }
        : {}),
      ...(isRecord(target.configuration) && Object.keys(target.configuration).length > 0
        ? { configuration: target.configuration }
        : {}),
      ...(Array.isArray(mission.waypoints) && mission.waypoints.length > 0
        ? { waypoints: mission.waypoints }
        : {}),
      ...(isRecord(parsed.profile) ? { profile: parsed.profile } : {}),
      ...(isRecord(parsed.scoring) ? { scoring: parsed.scoring } : {}),
    },
  };
}

// ---------------------------------------------------------------- generation

function parameterValue(parameter: ParameterDraft): string | number | null {
  const raw = parameter.value.trim();
  if (!raw) return null;
  if (parameter.kind === "duration") return raw;
  const numeric = Number(raw);
  return Number.isFinite(numeric) ? numeric : null;
}

function injectionBlock(event: EventDraft): Record<string, unknown> {
  const inject: Record<string, unknown> = {
    subsystem: event.subsystem,
    effect: event.effect,
  };
  if (event.duration.trim()) inject.duration = event.duration.trim();
  const parameters: Record<string, string | number> = {};
  for (const parameter of event.parameters) {
    const value = parameterValue(parameter);
    if (value !== null && parameter.name) parameters[parameter.name] = value;
  }
  if (Object.keys(parameters).length > 0) inject.parameters = parameters;
  return inject;
}

/** Build the canonical document object in the schema's key order. */
export function draftToDocument(draft: ScenarioDraft): Record<string, unknown> {
  const metadata: Record<string, unknown> = { name: draft.name };
  if (draft.description.trim()) metadata.description = draft.description.trim();
  metadata.version = draft.version || "1";
  if (draft.preserved.labels) metadata.labels = draft.preserved.labels;
  if (draft.tags.length > 0) metadata.tags = draft.tags;

  const target: Record<string, unknown> = { adapter: draft.adapter, vehicle: draft.vehicle };
  if (draft.preserved.configuration) target.configuration = draft.preserved.configuration;

  const mission: Record<string, unknown> = {
    type: draft.missionType,
    timeout: draft.timeout,
    altitude: draft.altitude,
    cruise_speed: draft.cruiseSpeed,
  };
  if (draft.preserved.waypoints) mission.waypoints = draft.preserved.waypoints;

  const document: Record<string, unknown> = {
    apiVersion: SCENARIO_API_VERSION,
    kind: SCENARIO_KIND,
    metadata,
    target,
    mission,
    recovery: {
      gnss_loss: draft.recovery.gnssLoss,
      datalink_loss: draft.recovery.datalinkLoss,
      compute_loss: draft.recovery.computeLoss,
      hold_timeout: draft.recovery.holdTimeout,
      max_dead_reckoning: draft.recovery.maxDeadReckoning,
    },
    simulation: {
      seed: draft.seed,
      speed: draft.speed,
      telemetry_rate_hz: draft.telemetryRateHz,
    },
  };
  if (draft.preserved.profile) document.profile = draft.preserved.profile;
  if (draft.events.length > 0) {
    document.events = draft.events.map((event) => {
      const entry: Record<string, unknown> = { id: event.id, at: event.at };
      if (event.description.trim()) entry.description = event.description.trim();
      entry.inject = injectionBlock(event);
      if (event.expect.length > 0) {
        entry.expect = event.expect.map((expectation) => {
          const item: Record<string, unknown> = {
            subsystem: expectation.subsystem,
            state: expectation.state,
            within: expectation.within,
          };
          if (expectation.description.trim()) item.description = expectation.description.trim();
          return item;
        });
      }
      return entry;
    });
  }
  if (draft.assertions.length > 0) {
    document.assertions = draft.assertions.map((assertion) => {
      const entry: Record<string, unknown> = {
        expression: assertion.expression,
        severity: assertion.severity,
      };
      if (assertion.description.trim()) entry.description = assertion.description.trim();
      return entry;
    });
  }
  if (draft.preserved.scoring) document.scoring = draft.preserved.scoring;
  return document;
}

export function draftToYaml(draft: ScenarioDraft): string {
  return dump(draftToDocument(draft), {
    lineWidth: 96,
    noRefs: true,
    sortKeys: false,
  });
}

// ---------------------------------------------------------------- schedule

export interface ScheduledInjection {
  id: string;
  at: number;
  subsystem: string;
  effect: string;
  duration: string | null;
  description: string;
  fromProfile: boolean;
}

const TRANSIENT_EFFECTS: readonly string[] = ["restart", "crash"];

/**
 * Explicit events plus the events a consequence profile expands into, ordered by time.
 * Mirrors `ResilienceScenario.expanded_events` so the countdown matches what will run.
 */
export function scenarioSchedule(draft: ScenarioDraft): ScheduledInjection[] {
  const schedule: ScheduledInjection[] = draft.events.map((event) => ({
    id: event.id,
    at: parseDuration(event.at) ?? 0,
    subsystem: event.subsystem,
    effect: event.effect,
    duration: event.duration || null,
    description: event.description,
    fromProfile: false,
  }));
  const profile = draft.preserved.profile;
  if (profile && isRecord(profile.effects)) {
    const at = parseDuration(asString(profile.at, "0s")) ?? 0;
    const duration = asString(profile.duration, "");
    const profileName = asString(profile.name, "profile");
    for (const [subsystem, behaviour] of Object.entries(profile.effects)) {
      if (behaviour === "operational" || typeof behaviour !== "string") continue;
      schedule.push({
        id: `${profileName}-${subsystem.replace(/[._]/g, "-")}`,
        at,
        subsystem,
        effect: behaviour,
        duration: TRANSIENT_EFFECTS.includes(behaviour) ? null : duration || null,
        description: `Consequence profile '${profileName}'`,
        fromProfile: true,
      });
    }
  }
  return schedule.sort((a, b) => a.at - b.at || a.id.localeCompare(b.id));
}

/** Parse a run's stored document, returning null instead of throwing. */
export function safeParseScenarioDocument(text: string | null | undefined): ScenarioDraft | null {
  if (!text) return null;
  try {
    return parseScenarioDocument(text);
  } catch {
    return null;
  }
}

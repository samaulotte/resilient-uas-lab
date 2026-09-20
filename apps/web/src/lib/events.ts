/**
 * Classification of run events for display.
 *
 * The distinction between what the scenario asked for, what was observed and how the
 * target reacted is the core of the analysis, so it is also a visual distinction.
 */

import type { EventKind, RunEvent, TelemetrySample } from "@reslab/api-client";

import { COMPONENT_STATE, EVENT_KIND, isHealthy, type Tone } from "@/lib/states";

export type EventClass = "injection" | "observed" | "response" | "verification" | "platform";

const CLASS_BY_KIND: Record<EventKind, EventClass> = {
  INJECTION_REQUEST: "injection",
  INJECTION_APPLIED: "injection",
  INJECTION_REJECTED: "injection",
  INJECTION_CLEARED: "injection",
  OBSERVED_EFFECT: "observed",
  RECOVERY: "observed",
  SYSTEM_RESPONSE: "response",
  EXPECTATION_RESULT: "verification",
  ASSERTION_RESULT: "verification",
  MISSION: "platform",
  LIFECYCLE: "platform",
  LOG: "platform",
};

export interface EventClassStyle {
  label: string;
  description: string;
  /** Left rail colour class applied to a feed row. */
  rail: string;
}

export const EVENT_CLASS: Record<EventClass, EventClassStyle> = {
  injection: {
    label: "Scenario",
    description: "Disturbance requested by the scenario",
    rail: "border-l-info",
  },
  observed: {
    label: "Observed",
    description: "State change measured in the target",
    rail: "border-l-warn",
  },
  response: {
    label: "Response",
    description: "Autonomous reaction of the target",
    rail: "border-l-ok",
  },
  verification: {
    label: "Check",
    description: "Declared expectation or assertion evaluated",
    rail: "border-l-border-strong",
  },
  platform: {
    label: "Platform",
    description: "Mission progress, lifecycle and logs",
    rail: "border-l-border",
  },
};

export function eventClass(event: RunEvent): EventClass {
  return CLASS_BY_KIND[event.kind];
}

/** Tone of an event row: failures dominate, then the kind's own tone. */
export function eventTone(event: RunEvent): Tone {
  if (event.kind === "OBSERVED_EFFECT" && event.state_after) {
    return COMPONENT_STATE[event.state_after].tone;
  }
  if (event.kind === "EXPECTATION_RESULT" || event.kind === "ASSERTION_RESULT") {
    return event.metadata?.passed === false ? "bad" : "ok";
  }
  return EVENT_KIND[event.kind].tone;
}

export function isStateChange(event: RunEvent): boolean {
  return event.state_after !== null && event.state_after !== undefined;
}

/** True when the event describes something the target did on its own. */
export function isSafeStateResponse(event: RunEvent): boolean {
  return event.kind === "SYSTEM_RESPONSE" && event.metadata?.safe_state === true;
}

export function eventMetadataNumber(event: RunEvent, key: string): number | null {
  const value = event.metadata?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export interface ActiveAlert {
  id: string;
  label: string;
  detail: string;
  tone: Tone;
}

const ALERT_LABELS: Record<string, string> = {
  "navigation.gnss": "GNSS",
  "navigation.estimator": "NAV",
  "communications.c2": "C2 LINK",
  "communications.telemetry": "TELEMETRY",
  "mission.compute": "MISSION COMPUTE",
  "mission.planner": "MISSION PLANNER",
  "mission.services": "MISSION SERVICES",
  "network.companion_link": "COMPANION LINK",
  "security.gateway": "CMD GATEWAY",
  "flight_control.core": "FLIGHT CORE",
  "actuation.motors": "MOTORS",
  "sensors.imu": "IMU",
  "sensors.barometer": "BAROMETER",
  "sensors.magnetometer": "MAGNETOMETER",
  "power.battery": "BATTERY",
  "power.bus": "POWER BUS",
  "external.gcs": "GROUND STATION",
};

const STATE_WORD: Record<string, string> = {
  DEGRADED: "DEGRADED",
  UNAVAILABLE: "LOST",
  FAILED: "FAILED",
  RECOVERING: "RESTARTING",
  UNKNOWN: "UNKNOWN",
};

/** Loud one-line alerts for every component that is not healthy right now. */
export function activeAlerts(sample: TelemetrySample | null, names: Map<string, string>): ActiveAlert[] {
  if (!sample?.health) return [];
  const alerts: ActiveAlert[] = [];
  for (const [id, state] of Object.entries(sample.health)) {
    if (isHealthy(state)) continue;
    const style = COMPONENT_STATE[state];
    const short = ALERT_LABELS[id] ?? (names.get(id) ?? id).toUpperCase();
    alerts.push({
      id,
      label: `${short} ${STATE_WORD[state] ?? state}`,
      detail: names.get(id) ?? id,
      tone: style.tone,
    });
  }
  if (sample.flight.mode === "HOLD" || sample.flight.mode === "RTL") {
    alerts.push({
      id: `flight-mode-${sample.flight.mode}`,
      label: sample.flight.mode === "HOLD" ? "FAILSAFE HOLD" : "RETURN TO LAUNCH",
      detail: `Autonomy: ${sample.flight.autonomy}`,
      tone: "warn",
    });
  }
  if (!sample.flight.control_authority) {
    alerts.push({
      id: "control-authority",
      label: "CONTROL AUTHORITY LOST",
      detail: "The flight core no longer has full control of the vehicle",
      tone: "bad",
    });
  }
  const order: Record<Tone, number> = { bad: 0, warn: 1, info: 2, ok: 3, dim: 4 };
  return alerts.sort((a, b) => order[a.tone] - order[b.tone]);
}

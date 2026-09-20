/**
 * Derived views over the observed data of a run.
 *
 * Everything here is computed from run events and telemetry, never from what the
 * scenario requested, so a live estimate and the analyzed metrics tell the same story.
 */

import { eventMetadataNumber, isSafeStateResponse } from "@/lib/events";
import { DOMAIN_ORDER, isHealthy } from "@/lib/states";
import type {
  ComponentState,
  Domain,
  RunEvent,
  TelemetrySample,
  TopologyComponent,
} from "@reslab/api-client";

export interface StateSegment {
  state: ComponentState;
  from: number;
  to: number;
}

export interface SubsystemTrack {
  subsystem: string;
  name: string;
  domain: Domain;
  critical: boolean;
  segments: StateSegment[];
  worst: ComponentState;
}

const SEVERITY_RANK: Record<ComponentState, number> = {
  FAILED: 5,
  UNAVAILABLE: 4,
  RECOVERING: 3,
  DEGRADED: 2,
  RECOVERED: 1,
  NOMINAL: 0,
  OPERATIONAL: 0,
  UNKNOWN: 0,
};

/**
 * Build one state timeline per subsystem from observed state transitions.
 *
 * Only subsystems that were actually observed changing state get a track, plus the
 * flight core, which is the component the safety case is about.
 */
export function buildTimeline(
  events: readonly RunEvent[],
  components: ReadonlyMap<string, TopologyComponent>,
  endTime: number,
  alwaysInclude: readonly string[] = ["flight_control.core"],
): SubsystemTrack[] {
  const transitions = new Map<string, { t: number; state: ComponentState }[]>();
  for (const event of events) {
    if (!event.subsystem || !event.state_after) continue;
    const list = transitions.get(event.subsystem);
    const entry = { t: event.simulation_time, state: event.state_after };
    if (list) list.push(entry);
    else transitions.set(event.subsystem, [entry]);
  }
  for (const id of alwaysInclude) {
    if (!transitions.has(id) && components.has(id)) transitions.set(id, []);
  }

  const tracks: SubsystemTrack[] = [];
  const end = Math.max(endTime, 0.001);
  for (const [subsystem, changes] of transitions) {
    const component = components.get(subsystem);
    const initial: ComponentState = component?.healthy_state ?? "NOMINAL";
    const segments: StateSegment[] = [];
    let current: ComponentState = initial;
    let from = 0;
    let worst: ComponentState = initial;
    for (const change of changes) {
      const at = Math.min(Math.max(change.t, 0), end);
      if (change.state === current) continue;
      if (at > from) segments.push({ state: current, from, to: at });
      current = change.state;
      from = at;
      if (SEVERITY_RANK[change.state] > SEVERITY_RANK[worst]) worst = change.state;
    }
    segments.push({ state: current, from, to: end });
    tracks.push({
      subsystem,
      name: component?.name ?? subsystem,
      domain: component?.domain ?? "mission_compute",
      critical: component?.critical ?? false,
      segments,
      worst,
    });
  }
  const order = new Map(DOMAIN_ORDER.map((domain, index) => [domain, index]));
  return tracks.sort((a, b) => {
    const domainDelta = (order.get(a.domain) ?? 99) - (order.get(b.domain) ?? 99);
    return domainDelta !== 0 ? domainDelta : a.name.localeCompare(b.name);
  });
}

export interface InjectionMarker {
  t: number;
  label: string;
  subsystem: string | null;
}

export function injectionMarkers(events: readonly RunEvent[]): InjectionMarker[] {
  return events
    .filter((event) => event.kind === "INJECTION_APPLIED")
    .map((event) => ({
      t: event.simulation_time,
      subsystem: event.subsystem ?? null,
      label: event.scenario_event_id ?? event.subsystem ?? "injection",
    }));
}

export interface LiveMissionKpis {
  progress: number;
  phase: string;
  flightMode: string;
  autonomy: string;
  safetyPreserved: boolean;
  controlAuthority: boolean;
  /** False while nothing was observed: no claim can be made about safety yet. */
  observed: boolean;
}

export interface LiveRecoveryKpis {
  faultsObserved: number;
  recovered: number;
  meanTimeToRecovery: number | null;
  timeToSafeState: number | null;
  safeStateEntered: boolean;
}

export interface LiveContainmentKpis {
  injectedComponents: string[];
  affectedComponents: string[];
  propagatedComponents: string[];
  affectedDomains: Domain[];
  flightDomainAffected: boolean;
  contained: boolean;
}

const CRITICAL_DOMAIN_SET: ReadonlySet<Domain> = new Set<Domain>(["flight_control", "actuation"]);

export function liveMissionKpis(
  sample: TelemetrySample | null,
  events: readonly RunEvent[],
): LiveMissionKpis {
  const flightCoreDown = events.some(
    (event) =>
      event.kind === "OBSERVED_EFFECT" &&
      event.subsystem === "flight_control.core" &&
      event.state_after !== null &&
      event.state_after !== undefined &&
      !isHealthy(event.state_after),
  );
  const controlAuthority = sample?.flight.control_authority ?? true;
  return {
    progress: sample?.mission.progress ?? 0,
    phase: sample?.mission.phase ?? "PENDING",
    flightMode: sample?.flight.mode ?? "UNKNOWN",
    autonomy: sample?.flight.autonomy ?? "mission",
    controlAuthority,
    safetyPreserved: controlAuthority && !flightCoreDown,
    observed: sample !== null || events.length > 0,
  };
}

export function liveRecoveryKpis(events: readonly RunEvent[]): LiveRecoveryKpis {
  const faults = new Set<string>();
  for (const event of events) {
    if (
      event.kind === "OBSERVED_EFFECT" &&
      event.subsystem &&
      event.state_after &&
      !isHealthy(event.state_after) &&
      // UNKNOWN is an observability gap (link down, not yet observed), not a fault, so it
      // must not count as an observed fault or, later, as a recovery.
      event.state_after !== "UNKNOWN"
    ) {
      faults.add(`${event.subsystem}@${event.simulation_time}`);
    }
  }
  const durations: number[] = [];
  let recovered = 0;
  for (const event of events) {
    if (event.kind !== "RECOVERY") continue;
    // Only a return from a genuinely impaired state is a recovery; a component coming back
    // from UNKNOWN (or with no prior fault state recorded) is regaining observation, not
    // recovering from a fault.
    if (!event.state_before || isHealthy(event.state_before) || event.state_before === "UNKNOWN") {
      continue;
    }
    recovered += 1;
    const duration = eventMetadataNumber(event, "fault_duration");
    if (duration !== null) durations.push(duration);
  }
  const safeStateEvent = events.find(isSafeStateResponse);
  let timeToSafeState: number | null = null;
  if (safeStateEvent) {
    const precedingFaults = events
      .filter(
        (event) =>
          event.kind === "OBSERVED_EFFECT" &&
          event.state_after !== null &&
          event.state_after !== undefined &&
          !isHealthy(event.state_after) &&
          event.simulation_time <= safeStateEvent.simulation_time,
      )
      .map((event) => event.simulation_time);
    const last = precedingFaults.at(-1);
    if (last !== undefined) {
      timeToSafeState = Math.round((safeStateEvent.simulation_time - last) * 1000) / 1000;
    }
  }
  return {
    faultsObserved: faults.size,
    recovered,
    meanTimeToRecovery:
      durations.length > 0
        ? Math.round((durations.reduce((sum, value) => sum + value, 0) / durations.length) * 100) /
          100
        : null,
    timeToSafeState,
    safeStateEntered: Boolean(safeStateEvent),
  };
}

export function liveContainmentKpis(
  events: readonly RunEvent[],
  components: ReadonlyMap<string, TopologyComponent>,
): LiveContainmentKpis {
  const injected = new Set<string>();
  const affected = new Set<string>();
  for (const event of events) {
    if (event.kind === "INJECTION_APPLIED" && event.subsystem) injected.add(event.subsystem);
    if (
      event.kind === "OBSERVED_EFFECT" &&
      event.subsystem &&
      event.state_after &&
      !isHealthy(event.state_after)
    ) {
      affected.add(event.subsystem);
    }
  }
  const affectedDomains = new Set<Domain>();
  for (const id of affected) {
    const domain = components.get(id)?.domain;
    if (domain) affectedDomains.add(domain);
  }
  const flightDomainAffected = [...affectedDomains].some((domain) =>
    CRITICAL_DOMAIN_SET.has(domain),
  );
  return {
    injectedComponents: [...injected].sort(),
    affectedComponents: [...affected].sort(),
    propagatedComponents: [...affected].filter((id) => !injected.has(id)).sort(),
    affectedDomains: DOMAIN_ORDER.filter((domain) => affectedDomains.has(domain)),
    flightDomainAffected,
    contained: !flightDomainAffected,
  };
}

/** Latest known state of every component, from telemetry with an event fallback. */
export function currentHealth(
  sample: TelemetrySample | null,
  events: readonly RunEvent[],
): Map<string, ComponentState> {
  const health = new Map<string, ComponentState>();
  for (const [id, state] of Object.entries(sample?.health ?? {})) health.set(id, state);
  if (health.size === 0) {
    for (const event of events) {
      if (event.subsystem && event.state_after) health.set(event.subsystem, event.state_after);
    }
  }
  return health;
}

/** Telemetry samples up to a simulation time, for replay. */
export function samplesUpTo(
  samples: readonly TelemetrySample[],
  time: number,
): readonly TelemetrySample[] {
  let low = 0;
  let high = samples.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    const sample = samples[mid];
    if (sample !== undefined && sample.t <= time) low = mid + 1;
    else high = mid;
  }
  return samples.slice(0, low);
}

export function eventsUpTo(events: readonly RunEvent[], time: number): RunEvent[] {
  return events.filter((event) => event.simulation_time <= time);
}

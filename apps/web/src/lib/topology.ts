/**
 * Helpers over the system topology returned by `GET /api/v1/system`.
 *
 * The topology is authoritative: component names, domains, dependencies and trust
 * boundaries are never hard-coded in the UI, only the presentation order is.
 */

import { DOMAIN_ORDER } from "@/lib/states";
import type { Domain, SystemTopology, TopologyComponent, TrustBoundary } from "@reslab/api-client";

export function componentNameMap(topology: SystemTopology | undefined): Map<string, string> {
  const map = new Map<string, string>();
  for (const component of topology?.components ?? []) map.set(component.id, component.name);
  return map;
}

export function componentMap(topology: SystemTopology | undefined): Map<string, TopologyComponent> {
  const map = new Map<string, TopologyComponent>();
  for (const component of topology?.components ?? []) map.set(component.id, component);
  return map;
}

export interface DomainGroup {
  domain: Domain;
  components: TopologyComponent[];
}

/** Components grouped by domain, in the platform's display order. */
export function groupByDomain(topology: SystemTopology | undefined): DomainGroup[] {
  const groups = new Map<Domain, TopologyComponent[]>();
  for (const component of topology?.components ?? []) {
    const list = groups.get(component.domain);
    if (list) list.push(component);
    else groups.set(component.domain, [component]);
  }
  return DOMAIN_ORDER.filter((domain) => groups.has(domain)).map((domain) => ({
    domain,
    components: groups.get(domain) ?? [],
  }));
}

/**
 * Command path from the ground station down to the actuators.
 *
 * This is the chain a fault has to walk to reach the flight-critical core, so it is the
 * chain the blast-radius panel renders.
 */
export const PROPAGATION_CHAIN: readonly string[] = [
  "external.gcs",
  "communications.c2",
  "communications.telemetry",
  "mission.compute",
  "mission.planner",
  "network.companion_link",
  "security.gateway",
  "flight_control.core",
  "actuation.motors",
];

/** The boundary a fault must not cross, with its enforcement point. */
export function missionFlightBoundary(
  topology: SystemTopology | undefined,
): TrustBoundary | undefined {
  return topology?.trust_boundaries.find((boundary) => boundary.id === "mission-flight");
}

export function isFlightCriticalZone(component: TopologyComponent | undefined): boolean {
  return component?.trust_zone === "flight_critical";
}

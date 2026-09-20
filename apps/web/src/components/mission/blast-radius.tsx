"use client";

import { ChevronDown, ShieldCheck } from "lucide-react";

import { DOMAIN_LABEL, DOMAIN_ORDER, isHealthy } from "@/lib/states";
import { PROPAGATION_CHAIN } from "@/lib/topology";
import { cn } from "@/lib/utils";
import type { ComponentState, Domain, TopologyComponent, TrustBoundary } from "@reslab/api-client";

type Role = "injected" | "propagated" | "protected" | "unaffected";

const ROLE_STYLE: Record<Role, { row: string; label: string; text: string }> = {
  injected: { row: "border-bad/70 bg-bad-soft", label: "INJECTED", text: "text-bad" },
  propagated: { row: "border-warn/70 bg-warn-soft", label: "PROPAGATED", text: "text-warn" },
  protected: { row: "border-ok/60 bg-transparent", label: "PROTECTED", text: "text-ok" },
  unaffected: { row: "border-border-strong bg-panel-2", label: "NOMINAL", text: "text-muted" },
};

/** Domains of the command path, from the ground station down to the actuators. */
const CHAIN_DOMAINS: readonly Domain[] = [
  "external",
  "communications",
  "mission_compute",
  "flight_control",
  "actuation",
];

/** Short labels so a domain never truncates in the narrow chain column. */
const CHAIN_LABEL: Partial<Record<Domain, string>> = {
  external: "EXTERNAL",
  communications: "COMMS",
  mission_compute: "MISSION",
  flight_control: "FLIGHT",
  actuation: "ACTUATION",
};

interface ChainRow {
  domain: Domain;
  role: Role;
  detail: string;
  title: string;
  enforcement: boolean;
}

/**
 * Where a fault stopped.
 *
 * The chain follows the command path grouped by domain, so the whole path from the
 * ground station to the actuators is visible at once. A domain holding an injection
 * target is red, one that only inherited the fault is amber, and a flight-critical
 * domain that stayed healthy while something upstream failed is outlined in green:
 * that is the containment claim being made.
 */
export function BlastRadius({
  components,
  injected,
  affected,
  health,
  boundary,
  affectedDomains,
  flightDomainAffected,
  className,
}: {
  components: ReadonlyMap<string, TopologyComponent>;
  injected: ReadonlySet<string>;
  affected: ReadonlySet<string>;
  health: ReadonlyMap<string, ComponentState>;
  boundary: TrustBoundary | undefined;
  affectedDomains: readonly Domain[];
  flightDomainAffected: boolean;
  className?: string;
}) {
  const anyFault = affected.size > 0;
  const enforcement = boundary?.enforcement_point;

  const rows: ChainRow[] = [];
  for (const domain of CHAIN_DOMAINS) {
    const ids = PROPAGATION_CHAIN.filter((id) => components.get(id)?.domain === domain);
    if (ids.length === 0) continue;
    const injectedIds = ids.filter((id) => injected.has(id));
    const affectedIds = ids.filter((id) => affected.has(id));
    const flightCritical = ids.some((id) => components.get(id)?.trust_zone === "flight_critical");
    const allHealthy = ids.every((id) => isHealthy(health.get(id)));
    const role: Role =
      injectedIds.length > 0
        ? "injected"
        : affectedIds.length > 0
          ? "propagated"
          : anyFault && flightCritical && allHealthy
            ? "protected"
            : "unaffected";
    const shown = affectedIds.length > 0 ? affectedIds : ids;
    const names = shown.map((id) => components.get(id)?.name ?? id);
    const head = names.slice(0, 2).join(", ");
    rows.push({
      domain,
      role,
      detail: names.length > 2 ? `${head} +${names.length - 2}` : head,
      title: ids
        .map((id) => `${components.get(id)?.name ?? id} (${id}): ${health.get(id) ?? "UNKNOWN"}`)
        .join("\n"),
      enforcement: typeof enforcement === "string" && ids.includes(enforcement),
    });
  }

  const lastHitIndex = rows.reduce(
    (last, row, index) => (row.role === "injected" || row.role === "propagated" ? index : last),
    -1,
  );
  const stopped = rows[lastHitIndex];

  const verdict = flightDomainAffected
    ? "BLAST RADIUS: PROPAGATED TO FLIGHT DOMAIN"
    : anyFault
      ? "BLAST RADIUS: CONTAINED"
      : "BLAST RADIUS: NO FAULT OBSERVED";
  const verdictTone = flightDomainAffected ? "text-bad" : anyFault ? "text-ok" : "text-dim";
  const subtitle = flightDomainAffected
    ? "A fault reached the flight-critical domain."
    : stopped
      ? `Stopped at ${DOMAIN_LABEL[stopped.domain]}.`
      : anyFault
        ? "No fault on the command path."
        : "No fault has been observed yet.";
  const affectedNames = affectedDomains.map((domain) => DOMAIN_LABEL[domain]).join(", ");

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="flex items-baseline justify-between gap-2">
        <span className={cn("mono text-[11px] font-semibold tracking-[0.05em]", verdictTone)}>
          {verdict}
        </span>
        <span className="mono shrink-0 text-[10.5px] text-muted">
          {affectedDomains.length} / {DOMAIN_ORDER.length} domains
        </span>
      </div>
      <p
        className="truncate text-[10.5px] text-dim"
        title={affectedNames ? `Affected domains: ${affectedNames}` : subtitle}
      >
        {subtitle}
        {affectedNames ? ` Affected: ${affectedNames}.` : ""}
      </p>

      <ol className="flex flex-col">
        {rows.map((row, index) => {
          const style = ROLE_STYLE[row.role];
          const showBoundary = boundary !== undefined && row.domain === "flight_control";
          const propagating = index < lastHitIndex;
          return (
            <li key={row.domain} className="flex flex-col">
              {showBoundary ? (
                <div className="flex items-center gap-1.5 py-[3px]">
                  <span className="h-px flex-1 border-t border-dashed border-info/70" />
                  <span
                    className="mono whitespace-nowrap text-[8.5px] uppercase tracking-[0.14em] text-info"
                    title={`${boundary.name}. ${boundary.description}`}
                  >
                    Trust boundary
                  </span>
                  <span className="h-px flex-1 border-t border-dashed border-info/70" />
                </div>
              ) : null}
              <div
                className={cn(
                  "flex h-[25px] items-center gap-1.5 rounded-sm border px-2",
                  style.row,
                )}
                title={row.title}
              >
                <span className="w-[62px] shrink-0 text-[9.5px] uppercase tracking-[0.06em] text-muted">
                  {CHAIN_LABEL[row.domain] ?? DOMAIN_LABEL[row.domain]}
                </span>
                <span className="min-w-0 flex-1 truncate text-[11px] text-foreground">
                  {row.detail}
                </span>
                {row.enforcement ? (
                  <ShieldCheck
                    size={11}
                    className="shrink-0 text-info"
                    aria-label="Policy enforcement point"
                  />
                ) : null}
                <span className={cn("mono shrink-0 text-[9px] tracking-[0.06em]", style.text)}>
                  {style.label}
                </span>
              </div>
              {index < rows.length - 1 &&
              !(boundary && rows[index + 1]?.domain === "flight_control") ? (
                <span
                  className={cn(
                    "flex h-[9px] items-center justify-center",
                    propagating ? "text-warn" : "text-border-strong",
                  )}
                  aria-hidden
                >
                  <ChevronDown size={10} />
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

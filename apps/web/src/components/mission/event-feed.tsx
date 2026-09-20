"use client";

import { EventKindBadge } from "@/components/ui/badge";
import { EVENT_CLASS, eventClass, eventTone, type ActiveAlert } from "@/lib/events";
import { SEVERITY, TONE_BG, TONE_TEXT } from "@/lib/states";
import { cn, formatMissionTime } from "@/lib/utils";
import type { RunEvent } from "@reslab/api-client";

/** Loud rows for everything that is not healthy right now. */
export function ActiveAlerts({ alerts }: { alerts: readonly ActiveAlert[] }) {
  if (alerts.length === 0) {
    return (
      <p className="flex items-center gap-2 px-1 py-2 text-[12px] text-ok">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-ok" aria-hidden />
        All observed subsystems nominal
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-1">
      {alerts.map((alert) => (
        <li
          key={alert.id}
          className={cn(
            "flex items-center justify-between gap-2 rounded-sm border px-2 py-[3px]",
            alert.tone === "bad" && "border-bad/50 bg-bad-soft",
            alert.tone === "warn" && "border-warn/50 bg-warn-soft",
            alert.tone === "info" && "border-info/50 bg-info-soft",
            alert.tone === "ok" && "border-ok/50 bg-ok-soft",
            alert.tone === "dim" && "border-border-strong bg-dim-soft",
          )}
        >
          <span
            className={cn(
              "mono text-[11.5px] font-semibold tracking-[0.06em]",
              TONE_TEXT[alert.tone],
            )}
          >
            {alert.label}
          </span>
          <span className="truncate text-[10.5px] text-muted" title={alert.detail}>
            {alert.detail}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function EventRow({ event, dense = false }: { event: RunEvent; dense?: boolean }) {
  const klass = eventClass(event);
  const tone = eventTone(event);
  const severity = SEVERITY[event.severity];
  return (
    <li
      className={cn(
        "flex items-start gap-2 border-l-2 px-2 hover:bg-panel-2/70",
        EVENT_CLASS[klass].rail,
        dense ? "py-[3px]" : "py-1",
      )}
    >
      <span className="mono w-[52px] shrink-0 text-[11px] text-dim">
        {formatMissionTime(event.simulation_time)}
      </span>
      <EventKindBadge kind={event.kind} size="xs" className="mt-[1px] shrink-0" />
      <span
        aria-label={`Severity ${severity.label}`}
        title={`Severity: ${severity.label}`}
        className={cn("mt-[6px] h-1.5 w-1.5 shrink-0 rounded-full", TONE_BG[severity.tone])}
      />
      <span className="min-w-0 flex-1">
        <span className={cn("block truncate text-[11.5px]", TONE_TEXT[tone])}>{event.message}</span>
        {event.subsystem ? (
          <span className="mono block truncate text-[10px] text-dim">{event.subsystem}</span>
        ) : null}
      </span>
    </li>
  );
}

/** Newest first live feed. Scenario, observed and response events are visually distinct. */
export function EventFeed({
  events,
  emptyLabel = "No events yet",
  dense = false,
  className,
}: {
  events: readonly RunEvent[];
  emptyLabel?: string;
  dense?: boolean;
  className?: string;
}) {
  if (events.length === 0) {
    return <p className={cn("px-2 py-4 text-[12px] text-muted", className)}>{emptyLabel}</p>;
  }
  return (
    <ul className={cn("flex flex-col divide-y divide-border/70", className)}>
      {events.map((event) => (
        <EventRow key={`${event.sequence}-${event.event_type}`} event={event} dense={dense} />
      ))}
    </ul>
  );
}

export function EventLegend() {
  return (
    <ul className="flex flex-wrap items-center gap-x-3 gap-y-1 px-2 py-1 text-[10px] text-dim">
      {(["injection", "observed", "response", "verification"] as const).map((klass) => (
        <li key={klass} className="flex items-center gap-1" title={EVENT_CLASS[klass].description}>
          <span
            aria-hidden
            className={cn(
              "inline-block h-2.5 w-0.5",
              EVENT_CLASS[klass].rail.replace("border-l-", "bg-"),
            )}
          />
          {EVENT_CLASS[klass].label}
        </li>
      ))}
    </ul>
  );
}

"use client";

import { Badge } from "@/components/ui/badge";
import type { ScheduledInjection } from "@/lib/scenario-document";
import { cn, formatDuration, formatMissionTime } from "@/lib/utils";

/**
 * The scenario schedule with a countdown against simulation time.
 *
 * A scheduled injection is a request, not evidence of a disturbance: rows only move to
 * "applied" once the adapter confirmed the effect in the observed event feed.
 */
export function UpcomingInjections({
  schedule,
  now,
  appliedIds,
  names,
}: {
  schedule: readonly ScheduledInjection[];
  now: number;
  appliedIds: ReadonlySet<string>;
  names: ReadonlyMap<string, string>;
}) {
  if (schedule.length === 0) {
    return <p className="px-2 py-4 text-[12px] text-muted">This scenario declares no injection.</p>;
  }
  return (
    <ul className="flex flex-col divide-y divide-border/70">
      {schedule.map((entry) => {
        const remaining = entry.at - now;
        const applied = appliedIds.has(entry.id);
        const pending = remaining > 0;
        return (
          <li
            key={entry.id}
            className={cn(
              "flex items-start gap-2 px-2 py-1",
              pending ? "opacity-100" : "opacity-70",
            )}
          >
            <span className="mono w-[52px] shrink-0 text-[11px] text-dim">
              {formatMissionTime(entry.at)}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5">
                <span className="mono truncate text-[11.5px] text-foreground">{entry.id}</span>
                {entry.fromProfile ? (
                  <Badge tone="dim" size="xs" title="Derived from a consequence profile">
                    PROFILE
                  </Badge>
                ) : null}
              </span>
              <span className="mono block truncate text-[10px] text-dim">
                {entry.effect} on {names.get(entry.subsystem) ?? entry.subsystem}
                {entry.duration ? ` for ${entry.duration}` : ""}
              </span>
            </span>
            {applied ? (
              <Badge tone="info" size="xs">
                APPLIED
              </Badge>
            ) : pending ? (
              <span className="mono shrink-0 text-[11px] text-warn" title="Time until requested">
                in {formatDuration(remaining)}
              </span>
            ) : (
              <Badge tone="dim" size="xs">
                DUE
              </Badge>
            )}
          </li>
        );
      })}
    </ul>
  );
}

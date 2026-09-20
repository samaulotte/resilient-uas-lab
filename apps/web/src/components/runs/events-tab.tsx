"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";

import { EventFeed, EventLegend } from "@/components/mission/event-feed";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { EVENT_KIND } from "@/lib/states";
import { cn } from "@/lib/utils";
import type { EventKind, RunEvent } from "@reslab/api-client";

const KIND_ORDER: readonly EventKind[] = [
  "INJECTION_REQUEST",
  "INJECTION_APPLIED",
  "INJECTION_REJECTED",
  "INJECTION_CLEARED",
  "OBSERVED_EFFECT",
  "SYSTEM_RESPONSE",
  "RECOVERY",
  "EXPECTATION_RESULT",
  "ASSERTION_RESULT",
  "MISSION",
  "LIFECYCLE",
  "LOG",
];

/** Full event list with kind chips and a free-text filter over message and subsystem. */
export function EventsTab({ events }: { events: readonly RunEvent[] }) {
  const [selected, setSelected] = useState<ReadonlySet<EventKind>>(new Set());
  const [search, setSearch] = useState("");

  const counts = useMemo(() => {
    const map = new Map<EventKind, number>();
    for (const event of events) map.set(event.kind, (map.get(event.kind) ?? 0) + 1);
    return map;
  }, [events]);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return events.filter((event) => {
      if (selected.size > 0 && !selected.has(event.kind)) return false;
      if (!needle) return true;
      return (
        event.message.toLowerCase().includes(needle) ||
        (event.subsystem ?? "").toLowerCase().includes(needle) ||
        event.event_type.toLowerCase().includes(needle) ||
        (event.scenario_event_id ?? "").toLowerCase().includes(needle)
      );
    });
  }, [events, selected, search]);

  const toggle = (kind: EventKind) => {
    const next = new Set(selected);
    if (next.has(kind)) next.delete(kind);
    else next.add(kind);
    setSelected(next);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-[260px]">
          <Search
            size={12}
            aria-hidden
            className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-dim"
          />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Filter by message, subsystem or event id"
            aria-label="Filter events"
            className="pl-6"
          />
        </div>
        <ul className="flex flex-wrap items-center gap-1">
          {KIND_ORDER.filter((kind) => counts.has(kind)).map((kind) => {
            const active = selected.has(kind);
            const style = EVENT_KIND[kind];
            return (
              <li key={kind}>
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => toggle(kind)}
                  title={`${style.label}: ${style.description}`}
                  className={cn(
                    "rounded-sm border px-1.5 py-[3px] text-[10px] font-semibold uppercase tracking-[0.07em] transition-colors",
                    active
                      ? "border-info bg-info-soft text-info"
                      : "border-border-strong bg-panel-2 text-muted hover:text-foreground",
                  )}
                >
                  {style.short}
                  <span className="mono ml-1 text-dim">{counts.get(kind)}</span>
                </button>
              </li>
            );
          })}
        </ul>
        {selected.size > 0 || search ? (
          <Button
            variant="ghost"
            size="xs"
            onClick={() => {
              setSelected(new Set());
              setSearch("");
            }}
          >
            Clear
          </Button>
        ) : null}
        <Badge tone="dim" size="xs" className="ml-auto">
          {filtered.length} of {events.length}
        </Badge>
      </div>
      <div className="panel">
        <EventLegend />
        <div className="max-h-[560px] overflow-y-auto border-t border-border">
          <EventFeed events={filtered} emptyLabel="No event matches this filter" />
        </div>
      </div>
    </div>
  );
}

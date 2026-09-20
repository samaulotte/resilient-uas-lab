"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, Search } from "lucide-react";

import { Input } from "@/components/ui/field";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { CatalogEntry, Effect } from "@reslab/api-client";

const CATEGORY_ORDER: readonly string[] = [
  "Navigation",
  "Sensors",
  "Communications",
  "Compute",
  "Process",
  "Network",
  "Power",
  "Security boundary",
  "Service",
];

/**
 * The authoritative whitelist of effects per subsystem.
 *
 * Clicking an effect appends an injection at the end of the timeline. Entries whose loss
 * means loss of the flight-critical function are marked: injecting there is a deliberate
 * test of the safety case, not a routine disturbance.
 */
export function FaultLibrary({
  catalog,
  onPick,
}: {
  catalog: readonly CatalogEntry[];
  onPick: (subsystem: string, effect: Effect) => void;
}) {
  const [search, setSearch] = useState("");

  const grouped = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const matches = catalog.filter(
      (entry) =>
        !needle ||
        entry.name.toLowerCase().includes(needle) ||
        entry.subsystem.toLowerCase().includes(needle) ||
        entry.effects.some((effect) => effect.includes(needle)),
    );
    const map = new Map<string, CatalogEntry[]>();
    for (const entry of matches) {
      const list = map.get(entry.category);
      if (list) list.push(entry);
      else map.set(entry.category, [entry]);
    }
    return [...map.entries()].sort(
      ([a], [b]) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b),
    );
  }, [catalog, search]);

  return (
    <div className="flex min-h-0 flex-col gap-2">
      <div className="relative">
        <Search
          size={12}
          aria-hidden
          className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-dim"
        />
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Filter subsystems and effects"
          aria-label="Filter the fault library"
          className="pl-6"
        />
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto pr-1">
        {grouped.length === 0 ? (
          <p className="px-1 py-3 text-[12px] text-muted">No subsystem matches this filter.</p>
        ) : null}
        {grouped.map(([category, entries]) => (
          <section key={category}>
            <h3 className="panel-title mb-1 text-[9px]">{category}</h3>
            <ul className="flex flex-col gap-1.5">
              {entries.map((entry) => (
                <li key={entry.subsystem} className="rounded-sm border border-border bg-panel-2 p-1.5">
                  <div className="mb-1 flex items-start gap-1">
                    {entry.critical ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span tabIndex={0} className="mt-[1px] shrink-0 text-warn">
                            <AlertTriangle size={11} aria-hidden />
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>
                          Flight critical. Injecting here targets the flight-critical domain and is
                          expected to fail the containment gate.
                        </TooltipContent>
                      </Tooltip>
                    ) : null}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[11.5px] text-foreground">
                        {entry.name}
                      </span>
                      <span className="mono block truncate text-[9.5px] text-dim">
                        {entry.subsystem}
                      </span>
                    </span>
                  </div>
                  {entry.effects.length === 0 ? (
                    <p className="text-[10px] text-dim">No effect can be injected here.</p>
                  ) : (
                    <ul className="flex flex-wrap gap-1">
                      {entry.effects.map((effect) => (
                        <li key={effect}>
                          <button
                            type="button"
                            onClick={() => onPick(entry.subsystem, effect)}
                            title={`Append '${effect}' on ${entry.name}`}
                            className={cn(
                              "mono rounded-sm border border-border-strong bg-panel px-1 py-[2px] text-[10px] text-muted transition-colors hover:border-info/60 hover:bg-info-soft hover:text-info",
                            )}
                          >
                            {effect}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}

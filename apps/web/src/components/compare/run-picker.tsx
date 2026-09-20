"use client";

import * as PopoverPrimitive from "@radix-ui/react-popover";
import { useMemo, useState } from "react";
import { Check, ChevronDown, Search } from "lucide-react";

import { ResultBadge } from "@/components/ui/badge";
import { Input } from "@/components/ui/field";
import { formatScore } from "@/lib/format";
import { cn, relativeTime, shortId } from "@/lib/utils";
import type { RunSummary } from "@reslab/api-client";

/** Searchable run selector: scenario, short id, score and result. */
export function RunPicker({
  label,
  runs,
  value,
  onChange,
  emptyLabel = "Select a run",
}: {
  label: string;
  runs: readonly RunSummary[];
  value: string | null;
  onChange: (runId: string) => void;
  emptyLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const selected = runs.find((run) => run.id === value);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return runs;
    return runs.filter(
      (run) =>
        run.scenario_name.toLowerCase().includes(needle) ||
        run.id.toLowerCase().includes(needle) ||
        run.label.toLowerCase().includes(needle) ||
        run.adapter.toLowerCase().includes(needle),
    );
  }, [runs, search]);

  return (
    <div className="flex flex-col gap-1">
      <span className="panel-title text-[9px]">{label}</span>
      <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
        <PopoverPrimitive.Trigger
          className={cn(
            "flex h-8 w-full items-center justify-between gap-2 rounded-sm border border-border-strong bg-panel-2 px-2 text-[12px] transition-colors hover:border-info/50",
            selected ? "text-foreground" : "text-dim",
          )}
          aria-label={label}
        >
          {selected ? (
            <span className="flex min-w-0 items-center gap-2">
              <span className="mono text-info">{shortId(selected.id)}</span>
              <span className="truncate">{selected.scenario_name}</span>
              <span className="mono text-muted">{formatScore(selected.resilience_score)}</span>
            </span>
          ) : (
            <span>{emptyLabel}</span>
          )}
          <ChevronDown size={13} className="shrink-0 text-dim" aria-hidden />
        </PopoverPrimitive.Trigger>
        <PopoverPrimitive.Portal>
          <PopoverPrimitive.Content
            align="start"
            sideOffset={4}
            className="z-50 w-[var(--radix-popover-trigger-width)] min-w-[380px] rounded-sm border border-border-strong bg-panel-2 shadow-xl"
          >
            <div className="relative border-b border-border p-1.5">
              <Search
                size={12}
                aria-hidden
                className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-dim"
              />
              <Input
                autoFocus
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search by scenario, id, adapter or label"
                aria-label={`Search runs for ${label}`}
                className="pl-6"
              />
            </div>
            <ul className="max-h-[320px] overflow-y-auto p-1">
              {filtered.length === 0 ? (
                <li className="px-2 py-3 text-[12px] text-muted">No completed run matches.</li>
              ) : null}
              {filtered.map((run) => (
                <li key={run.id}>
                  <button
                    type="button"
                    onClick={() => {
                      onChange(run.id);
                      setOpen(false);
                    }}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-sm px-2 py-1 text-left text-[11.5px] transition-colors hover:bg-info-soft",
                      run.id === value && "bg-info-soft",
                    )}
                  >
                    <span className="w-3 shrink-0 text-info">
                      {run.id === value ? <Check size={11} aria-hidden /> : null}
                    </span>
                    <span className="mono shrink-0 text-info">{shortId(run.id)}</span>
                    <span className="min-w-0 flex-1 truncate text-foreground">
                      {run.scenario_name}
                    </span>
                    <span className="mono shrink-0 text-muted">
                      {formatScore(run.resilience_score)}
                    </span>
                    <ResultBadge result={run.result} size="xs" />
                    <span className="shrink-0 text-[10px] text-dim">
                      {relativeTime(run.created_at)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </PopoverPrimitive.Content>
        </PopoverPrimitive.Portal>
      </PopoverPrimitive.Root>
    </div>
  );
}

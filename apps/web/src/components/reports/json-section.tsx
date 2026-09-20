"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

/** Collapsible pretty-printed JSON section of a report. */
export function JsonSection({
  title,
  value,
  defaultOpen = false,
  description,
}: {
  title: string;
  value: unknown;
  defaultOpen?: boolean;
  description?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const empty = value === undefined || value === null;
  return (
    <section className="border-b border-border last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-left transition-colors hover:bg-panel-2"
      >
        {open ? (
          <ChevronDown size={12} className="text-dim" aria-hidden />
        ) : (
          <ChevronRight size={12} className="text-dim" aria-hidden />
        )}
        <span className="panel-title">{title}</span>
        {description ? <span className="text-[10.5px] text-dim">{description}</span> : null}
        {empty ? <span className="ml-auto text-[10px] text-dim">not present</span> : null}
      </button>
      {open && !empty ? (
        <pre
          className={cn(
            "mono max-h-[420px] overflow-auto border-t border-border bg-elevated px-3 py-2 text-[11px] leading-relaxed text-foreground",
          )}
        >
          {JSON.stringify(value, null, 2)}
        </pre>
      ) : null}
    </section>
  );
}

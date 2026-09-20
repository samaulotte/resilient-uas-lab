"use client";

import { ShieldAlert } from "lucide-react";

import { ComponentStateBadge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { DOMAIN_LABEL, isHealthy } from "@/lib/states";
import type { DomainGroup } from "@/lib/topology";
import { cn } from "@/lib/utils";
import type { ComponentState } from "@reslab/api-client";

/**
 * Subsystem states grouped by domain in topology order. Flight-critical components
 * carry a marker: losing one of them is losing the flight-critical function.
 */
export function SystemPanel({
  groups,
  health,
  className,
}: {
  groups: readonly DomainGroup[];
  health: ReadonlyMap<string, ComponentState>;
  className?: string;
}) {
  if (groups.length === 0) {
    return (
      <p className={cn("px-3 py-6 text-center text-[12px] text-muted", className)}>
        The system topology is not available.
      </p>
    );
  }
  return (
    <div className={cn("flex flex-col gap-2.5", className)}>
      {groups.map((group) => (
        <section key={group.domain}>
          <h3 className="panel-title mb-1 flex items-center gap-1.5 text-[9px]">
            <span className="h-px flex-1 bg-border" aria-hidden />
            <span>{DOMAIN_LABEL[group.domain]}</span>
            <span className="h-px flex-[6] bg-border" aria-hidden />
          </h3>
          <ul className="flex flex-col">
            {group.components.map((component) => {
              const state = health.get(component.id);
              const degraded = state !== undefined && !isHealthy(state);
              return (
                <li
                  key={component.id}
                  className={cn(
                    "flex items-center justify-between gap-2 rounded-sm px-1 py-[3px]",
                    degraded && "bg-panel-2",
                  )}
                >
                  <span className="flex min-w-0 items-center gap-1">
                    {component.critical ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span tabIndex={0} className="shrink-0 text-warn" aria-label="Flight critical">
                            <ShieldAlert size={11} aria-hidden />
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>
                          Flight critical: losing this component means losing the flight-critical
                          function.
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      <span className="w-[11px] shrink-0" aria-hidden />
                    )}
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span
                          tabIndex={0}
                          className="truncate text-[11.5px] text-foreground"
                          title={component.name}
                        >
                          {component.name}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>
                        <span className="mono text-[11px] text-info">{component.id}</span>
                        {component.description ? (
                          <span className="mt-1 block text-muted">{component.description}</span>
                        ) : null}
                      </TooltipContent>
                    </Tooltip>
                  </span>
                  <ComponentStateBadge state={state} size="xs" />
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

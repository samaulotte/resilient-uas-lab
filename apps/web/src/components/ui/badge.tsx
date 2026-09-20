import { cva, type VariantProps } from "class-variance-authority";

import {
  BENCHMARK_RESULT,
  COMPONENT_STATE,
  EVENT_KIND,
  FLIGHT_MODE,
  RUN_STATE,
  SEVERITY,
  type Tone,
} from "@/lib/states";
import { cn } from "@/lib/utils";
import type {
  BenchmarkResult,
  ComponentState,
  EventKind,
  FlightMode,
  RunState,
  Severity,
} from "@reslab/api-client";

const badgeVariants = cva(
  "inline-flex items-center gap-1 whitespace-nowrap rounded-sm border font-semibold uppercase leading-none tracking-[0.07em]",
  {
    variants: {
      tone: {
        ok: "border-ok/40 bg-ok-soft text-ok",
        warn: "border-warn/40 bg-warn-soft text-warn",
        bad: "border-bad/40 bg-bad-soft text-bad",
        info: "border-info/40 bg-info-soft text-info",
        dim: "border-border-strong bg-dim-soft text-muted",
      },
      size: {
        xs: "px-1 py-[2px] text-[9.5px]",
        sm: "px-1.5 py-[3px] text-[10px]",
        md: "px-2 py-[4px] text-[11px]",
      },
      solid: {
        true: "border-transparent",
        false: "",
      },
    },
    compoundVariants: [
      { solid: true, tone: "ok", class: "bg-ok/90 text-background" },
      { solid: true, tone: "warn", class: "bg-warn/90 text-background" },
      { solid: true, tone: "bad", class: "bg-bad/90 text-background" },
      { solid: true, tone: "info", class: "bg-info/90 text-background" },
      { solid: true, tone: "dim", class: "bg-dim/70 text-background" },
    ],
    defaultVariants: { tone: "dim", size: "sm", solid: false },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {
  tone?: Tone;
}

export function Badge({ className, tone, size, solid, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone, size, solid }), className)} {...props} />;
}

type BadgeSize = NonNullable<BadgeProps["size"]>;

interface StateBadgeProps {
  size?: BadgeSize;
  className?: string;
}

export function ComponentStateBadge({
  state,
  size,
  className,
}: StateBadgeProps & { state: ComponentState | null | undefined }) {
  const style = state ? COMPONENT_STATE[state] : COMPONENT_STATE.UNKNOWN;
  return (
    <Badge tone={style.tone} size={size} className={className} title={style.description}>
      {style.label}
    </Badge>
  );
}

export function RunStateBadge({ state, size, className }: StateBadgeProps & { state: RunState }) {
  const style = RUN_STATE[state];
  return (
    <Badge tone={style.tone} size={size} className={className} title={style.description}>
      {style.label}
    </Badge>
  );
}

export function ResultBadge({
  result,
  size,
  className,
}: StateBadgeProps & { result: BenchmarkResult | null | undefined }) {
  if (!result) {
    return (
      <Badge tone="dim" size={size} className={className} title="Run not analyzed">
        NOT ANALYZED
      </Badge>
    );
  }
  const style = BENCHMARK_RESULT[result];
  return (
    <Badge tone={style.tone} size={size} className={className} title={style.description}>
      {style.label}
    </Badge>
  );
}

export function SeverityBadge({
  severity,
  size,
  className,
}: StateBadgeProps & { severity: Severity }) {
  const style = SEVERITY[severity];
  return (
    <Badge tone={style.tone} size={size} className={className} title={style.description}>
      {style.label}
    </Badge>
  );
}

export function EventKindBadge({ kind, size, className }: StateBadgeProps & { kind: EventKind }) {
  const style = EVENT_KIND[kind];
  return (
    <Badge
      tone={style.tone}
      size={size}
      className={cn("mono", className)}
      title={`${style.label}: ${style.description}`}
    >
      {style.short}
    </Badge>
  );
}

export function FlightModeBadge({ mode, size, className }: StateBadgeProps & { mode: FlightMode }) {
  const style = FLIGHT_MODE[mode];
  return (
    <Badge tone={style.tone} size={size} className={className} title={style.description}>
      {style.label}
    </Badge>
  );
}

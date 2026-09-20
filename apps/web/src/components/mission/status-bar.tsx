"use client";

import Link from "next/link";
import { ExternalLink, Square } from "lucide-react";

import { Badge, ResultBadge, RunStateBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { apiUrl } from "@/lib/api";
import { formatScore } from "@/lib/format";
import { TONE_BG, TONE_TEXT } from "@/lib/states";
import { connectionLabel, connectionTone, type ConnectionStatus } from "@/stores/live-run";
import { cn, formatMissionTime, formatPercent, shortId } from "@/lib/utils";
import type { AdapterInfo, RunDetail } from "@reslab/api-client";

function Cell({
  label,
  children,
  className,
  title,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-0.5 px-3 py-1.5", className)} title={title}>
      <span className="panel-title text-[9px]">{label}</span>
      <span className="truncate text-[12px] leading-4 text-foreground">{children}</span>
    </div>
  );
}

export function StatusBar({
  run,
  adapter,
  connection,
  simulationTime,
  progress,
  speed,
  onCancel,
  cancelPending,
  canCancel,
  reportAvailable,
}: {
  run: RunDetail;
  adapter: AdapterInfo | undefined;
  connection: ConnectionStatus;
  simulationTime: number;
  progress: number;
  speed: number;
  onCancel: () => void;
  cancelPending: boolean;
  canCancel: boolean;
  reportAvailable: boolean;
}) {
  const tone = connectionTone(connection);
  return (
    <section className="panel flex items-stretch gap-0 overflow-hidden" aria-label="Run status">
      <div className="flex items-center gap-2 border-r border-border bg-panel-2 px-3 py-1.5">
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="flex flex-col gap-0.5" tabIndex={0}>
              <span className="panel-title text-[9px]">Adapter</span>
              <span className="text-[12px] font-medium text-foreground">
                {adapter?.display_name ?? run.adapter}
              </span>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            <span className="block font-medium text-foreground">
              Data origin: {adapter?.data_origin ?? "unknown"}
            </span>
            {adapter?.description ? (
              <span className="mt-1 block text-muted">{adapter.description}</span>
            ) : null}
          </TooltipContent>
        </Tooltip>
        <Badge tone="info" size="xs" title={`Data origin: ${adapter?.data_origin ?? "unknown"}`}>
          {adapter?.data_origin ?? run.adapter}
        </Badge>
      </div>

      <Cell label="Scenario" className="max-w-[240px]">
        <Link href={`/scenarios/${run.scenario_name}`} className="hover:text-info hover:underline">
          {run.scenario_name}
        </Link>
        <span className="mono ml-1 text-[10.5px] text-dim">v{run.scenario_version}</span>
      </Cell>

      <Cell label="Run">
        <Link href={`/runs/${run.id}`} className="mono hover:text-info hover:underline">
          {shortId(run.id)}
        </Link>
      </Cell>

      <div className="flex items-center gap-2 px-3 py-1.5" data-testid="run-state">
        <RunStateBadge state={run.state} size="sm" />
        {run.result ? <ResultBadge result={run.result} size="sm" /> : null}
        {run.resilience_score !== null ? (
          <span className="mono text-[12px] text-foreground" title="Resilience score">
            {formatScore(run.resilience_score)}
          </span>
        ) : null}
      </div>

      <Cell label="Simulation time">
        <span className="mono" data-testid="simulation-time">
          {formatMissionTime(simulationTime)}
        </span>
      </Cell>

      <Cell label="Speed" title="Simulation speed factor">
        <span className="mono">{speed}x</span>
      </Cell>

      <div className="flex min-w-[150px] flex-1 flex-col justify-center gap-1 px-3 py-1.5">
        <div className="flex items-center justify-between">
          <span className="panel-title text-[9px]">Mission progress</span>
          <span className="mono text-[11px] text-muted">{formatPercent(progress, 0)}</span>
        </div>
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-panel-3"
          role="progressbar"
          aria-valuenow={Math.round(progress * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Mission progress"
        >
          <div
            className="h-full rounded-full bg-info transition-[width] duration-500"
            style={{ width: `${Math.min(100, Math.max(0, progress * 100))}%` }}
          />
        </div>
      </div>

      <div className="flex items-center gap-2 border-l border-border bg-panel-2 px-3 py-1.5">
        <span
          className="flex items-center gap-1.5"
          role="status"
          aria-live="polite"
          title="Live stream connection"
        >
          <span
            aria-hidden
            className={cn(
              "inline-block h-2 w-2 rounded-full",
              TONE_BG[tone],
              (connection === "connecting" || connection === "reconnecting") && "pulse-soft",
            )}
          />
          <span className={cn("mono text-[11px] tracking-[0.08em]", TONE_TEXT[tone])}>
            {connectionLabel(connection)}
          </span>
        </span>
        {canCancel ? (
          <Button variant="danger" size="xs" onClick={onCancel} disabled={cancelPending}>
            <Square size={10} aria-hidden />
            {cancelPending ? "Cancelling" : "Cancel"}
          </Button>
        ) : null}
        {reportAvailable ? (
          <Button asChild variant="outline" size="xs">
            <a href={apiUrl(`/api/v1/runs/${run.id}/report.html`)} target="_blank" rel="noreferrer">
              Report
              <ExternalLink size={10} aria-hidden />
            </a>
          </Button>
        ) : null}
      </div>
    </section>
  );
}

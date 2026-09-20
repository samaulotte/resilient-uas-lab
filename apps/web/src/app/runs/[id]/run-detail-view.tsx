"use client";

import Link from "next/link";
import { useMemo } from "react";
import { ExternalLink, Radar, Square } from "lucide-react";

import { ArtifactsTab } from "@/components/runs/artifacts-tab";
import { AssertionsTable } from "@/components/runs/assertions-table";
import { EventsTab } from "@/components/runs/events-tab";
import { MetricsTab } from "@/components/runs/metrics-tab";
import { ProvenanceTab } from "@/components/runs/provenance-tab";
import { ReplayTab } from "@/components/runs/replay-tab";
import { HardGates, ScoreBreakdown } from "@/components/runs/score-breakdown";
import { TelemetryChart } from "@/components/runs/telemetry-chart";
import { Badge, ResultBadge, RunStateBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState, LoadingPanel, Notice, SkeletonRows } from "@/components/ui/feedback";
import { Field, Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useCancelRun,
  useRun,
  useRunEvents,
  useRunMetrics,
  useRunTelemetry,
} from "@/hooks/use-runs";
import { useSystemInfo } from "@/hooks/use-system";
import { apiUrl } from "@/lib/api";
import { formatScore } from "@/lib/format";
import { ACTIVE_RUN_STATES } from "@/lib/states";
import { cn, formatDateTime, formatDuration, shortId } from "@/lib/utils";
import { isTerminalRunState, type ReportSummary } from "@reslab/api-client";

function SummaryItem({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "ok" | "warn" | "bad";
}) {
  return (
    <div className="flex flex-col gap-0.5 rounded-sm border border-border bg-panel-2 px-2.5 py-1.5">
      <span className="panel-title text-[9px]">{label}</span>
      <span
        className={cn(
          "mono text-[14px]",
          tone === "ok" && "text-ok",
          tone === "warn" && "text-warn",
          tone === "bad" && "text-bad",
          !tone && "text-foreground",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function SummaryGrid({ summary }: { summary: ReportSummary }) {
  return (
    <div className="grid grid-cols-5 gap-2">
      <SummaryItem
        label="Mission complete"
        value={summary.mission_complete ? "yes" : "no"}
        tone={summary.mission_complete ? "ok" : "warn"}
      />
      <SummaryItem
        label="Faults injected / applied"
        value={`${summary.faults_injected} / ${summary.faults_applied}`}
      />
      <SummaryItem
        label="Critical failures"
        value={String(summary.critical_failures)}
        tone={summary.critical_failures > 0 ? "bad" : "ok"}
      />
      <SummaryItem label="Recovered subsystems" value={String(summary.recovered_subsystems)} />
      <SummaryItem label="Degraded transitions" value={String(summary.degraded_transitions)} />
      <SummaryItem
        label="Loss of control"
        value={summary.loss_of_control ? "yes" : "no"}
        tone={summary.loss_of_control ? "bad" : "ok"}
      />
      <SummaryItem
        label="Safety preservation"
        value={summary.safety_preservation}
        tone={summary.safety_preservation === "PASS" ? "ok" : "bad"}
      />
      <SummaryItem
        label="Fault containment"
        value={summary.fault_containment}
        tone={summary.fault_containment === "PASS" ? "ok" : "bad"}
      />
      <SummaryItem
        label="Mean time to recovery"
        value={
          summary.mean_time_to_recovery === null
            ? "n/a"
            : formatDuration(summary.mean_time_to_recovery)
        }
      />
      <SummaryItem label="Affected domains" value={`${summary.affected_domains} / 7`} />
    </div>
  );
}

export function RunDetailView({ runId }: { runId: string }) {
  const system = useSystemInfo();
  const cancelRun = useCancelRun();

  const runQuery = useRun(runId, { poll: true });
  const run = runQuery.data;
  const terminal = run ? isTerminalRunState(run.state) : false;
  const active = run ? ACTIVE_RUN_STATES.includes(run.state) || run.state === "QUEUED" : false;

  const eventsQuery = useRunEvents(runId, Boolean(run));
  const telemetryQuery = useRunTelemetry(runId, Boolean(run));
  const metricsQuery = useRunMetrics(runId, run?.state === "COMPLETED");

  const events = useMemo(() => eventsQuery.data?.events ?? [], [eventsQuery.data]);
  const samples = useMemo(() => telemetryQuery.data?.samples ?? [], [telemetryQuery.data]);
  const adapter = system.data?.adapters.find((entry) => entry.name === run?.adapter);

  if (runQuery.isError) {
    return (
      <div className="p-4">
        <ErrorState
          title="Run not found"
          error={runQuery.error}
          onRetry={() => void runQuery.refetch()}
        />
      </div>
    );
  }

  if (!run) {
    return <LoadingPanel label="Loading run" className="p-4" />;
  }

  const metrics = metricsQuery.data;

  return (
    <div className="flex flex-col gap-3 p-4">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[15px] font-semibold text-foreground">{run.scenario_name}</h1>
          <span className="mono text-[11px] text-dim" title={run.id}>
            {shortId(run.id)}
          </span>
          <RunStateBadge state={run.state} size="sm" />
          <ResultBadge result={run.result} size="sm" />
          {run.resilience_score !== null ? (
            <span className="mono text-[13px] text-foreground" title="Resilience score">
              {formatScore(run.resilience_score)}
            </span>
          ) : null}
          {run.label ? (
            <Badge tone="dim" size="xs">
              {run.label}
            </Badge>
          ) : null}
          <div className="ml-auto flex items-center gap-2">
            {active ? (
              <>
                <Button asChild variant="primary" size="sm">
                  <Link href={`/mission-control?run=${run.id}`}>
                    <Radar size={11} aria-hidden />
                    Open in Mission Control
                  </Link>
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => cancelRun.mutate(run.id)}
                  disabled={cancelRun.isPending}
                >
                  <Square size={10} aria-hidden />
                  {cancelRun.isPending ? "Cancelling" : "Cancel run"}
                </Button>
              </>
            ) : (
              <Button asChild variant="outline" size="sm">
                <Link href={`/mission-control?run=${run.id}`}>Open in Mission Control</Link>
              </Button>
            )}
            {run.report_available ? (
              <Button asChild variant="outline" size="sm">
                <a
                  href={apiUrl(`/api/v1/runs/${run.id}/report.html`)}
                  target="_blank"
                  rel="noreferrer"
                >
                  HTML report
                  <ExternalLink size={10} aria-hidden />
                </a>
              </Button>
            ) : null}
          </div>
        </div>

        <div className="panel grid grid-cols-8 gap-x-4 gap-y-2 px-3 py-2">
          <Field label="Adapter" hint={adapter?.description}>
            {adapter?.display_name ?? run.adapter}
          </Field>
          <Field label="Data origin">{adapter?.data_origin ?? "unknown"}</Field>
          <Field label="Vehicle">{run.vehicle}</Field>
          <Field label="Seed">
            <span className="mono">{run.seed}</span>
          </Field>
          <Field label="Speed">
            <span className="mono">{run.speed}x</span>
          </Field>
          <Field label="Runner">
            <span className="mono">{run.runner_id ?? "not assigned"}</span>
          </Field>
          <Field label="Hard gate">
            <ResultBadge result={run.hard_gate_result} size="xs" />
          </Field>
          <Field label="Simulation duration">
            <span className="mono">{formatDuration(run.last_simulation_time)}</span>
          </Field>
          <Field label="Created">{formatDateTime(run.created_at)}</Field>
          <Field label="Started">{formatDateTime(run.started_at)}</Field>
          <Field label="Ended">{formatDateTime(run.ended_at)}</Field>
          <Field label="Events">
            <span className="mono">{run.event_count}</span>
          </Field>
          <Field label="Telemetry samples">
            <span className="mono">{run.sample_count}</span>
          </Field>
          <Field label="Scenario version">
            <span className="mono">v{run.scenario_version}</span>
          </Field>
          <Field label="Scenario hash" hint={run.scenario_hash}>
            <span className="mono">{run.scenario_hash.replace("sha256:", "").slice(0, 12)}</span>
          </Field>
          <Field label="Replay source">
            {run.replay_source_run_id ? (
              <Link
                href={`/runs/${run.replay_source_run_id}`}
                className="mono text-info hover:underline"
              >
                {shortId(run.replay_source_run_id)}
              </Link>
            ) : (
              "original run"
            )}
          </Field>
        </div>

        {run.reason ? (
          <Notice
            tone={run.state === "FAILED" ? "bad" : run.state === "CANCELLED" ? "warn" : "info"}
          >
            {run.reason}
          </Notice>
        ) : null}
      </header>

      <Tabs defaultValue="overview" className="flex flex-col gap-3">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="replay">Replay</TabsTrigger>
          <TabsTrigger value="events">Events</TabsTrigger>
          <TabsTrigger value="metrics">Metrics</TabsTrigger>
          <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
          <TabsTrigger value="provenance">Provenance</TabsTrigger>
          <TabsTrigger value="scenario">Scenario</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="flex flex-col gap-3">
          {run.summary ? (
            <SummaryGrid summary={run.summary} />
          ) : (
            <Notice tone="info">
              The summary is produced by the analysis once the run completes.
            </Notice>
          )}
          {telemetryQuery.isLoading ? null : <TelemetryChart samples={samples} events={events} />}
          {metricsQuery.isLoading && run.state === "COMPLETED" ? (
            <SkeletonRows rows={6} />
          ) : metrics ? (
            <>
              <Panel>
                <PanelHeader>
                  <PanelTitle>Score breakdown</PanelTitle>
                  <span className="ml-auto mono text-[11px] text-muted">
                    profile {metrics.score.profile.name}
                  </span>
                </PanelHeader>
                <PanelBody className="p-0">
                  <ScoreBreakdown score={metrics.score} />
                </PanelBody>
              </Panel>
              <Panel>
                <PanelHeader>
                  <PanelTitle>Hard gates</PanelTitle>
                  <span className="ml-auto text-[10px] text-dim">
                    A failed gate fails the run whatever the score
                  </span>
                </PanelHeader>
                <PanelBody className="p-2.5">
                  <HardGates score={metrics.score} />
                </PanelBody>
              </Panel>
              <Panel>
                <PanelHeader>
                  <PanelTitle>Assertions</PanelTitle>
                </PanelHeader>
                <PanelBody className="p-0">
                  <AssertionsTable assertions={metrics.assertions} />
                </PanelBody>
              </Panel>
            </>
          ) : (
            <Notice tone={run.state === "COMPLETED" ? "warn" : "info"}>
              {run.state === "COMPLETED"
                ? "The analysis is not available for this run."
                : "Metrics, score and assertions are computed once the run completes."}
            </Notice>
          )}
        </TabsContent>

        <TabsContent value="replay">
          {telemetryQuery.isLoading ? (
            <LoadingPanel label="Loading recorded telemetry" />
          ) : (
            <ReplayTab
              key={`${run.id}-${samples.length}`}
              samples={samples}
              events={events}
              plannedPath={run.planned_path}
              topology={system.data?.topology}
              duration={Math.max(run.last_simulation_time, 1)}
            />
          )}
        </TabsContent>

        <TabsContent value="events">
          {eventsQuery.isLoading ? <SkeletonRows rows={10} /> : <EventsTab events={events} />}
        </TabsContent>

        <TabsContent value="metrics">
          {metrics ? (
            <MetricsTab metrics={metrics.metrics} />
          ) : (
            <Notice tone="info">
              Metrics are computed by the analysis once the run completes.
            </Notice>
          )}
        </TabsContent>

        <TabsContent value="artifacts">
          <ArtifactsTab
            artifacts={run.artifacts}
            runId={run.id}
            reportAvailable={run.report_available}
          />
        </TabsContent>

        <TabsContent value="provenance">
          <ProvenanceTab provenance={run.provenance} />
        </TabsContent>

        <TabsContent value="scenario">
          <Panel>
            <PanelHeader>
              <PanelTitle>Scenario document</PanelTitle>
              <span className="ml-auto text-[10px] text-dim">
                Executed exactly as recorded, read only
              </span>
              <Button asChild variant="ghost" size="xs">
                <Link href={`/scenarios/${run.scenario_name}`}>Open in the studio</Link>
              </Button>
            </PanelHeader>
            <PanelBody className="p-0">
              <pre className="mono max-h-[640px] overflow-auto p-3 text-[11.5px] leading-relaxed text-foreground">
                {run.scenario_document}
              </pre>
            </PanelBody>
          </Panel>
        </TabsContent>
      </Tabs>

      {terminal ? null : (
        <p className="text-[11px] text-dim">
          This run is still active. The page refreshes every few seconds.
        </p>
      )}
    </div>
  );
}

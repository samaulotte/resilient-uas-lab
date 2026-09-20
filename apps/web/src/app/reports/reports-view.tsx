"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Download, ExternalLink, FileText } from "lucide-react";

import { JsonSection } from "@/components/reports/json-section";
import { ResultBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingPanel, SkeletonRows } from "@/components/ui/feedback";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { api, apiUrl, unwrap } from "@/lib/api";
import { formatBytes, formatScore } from "@/lib/format";
import { useRun, useRuns } from "@/hooks/use-runs";
import { cn, formatDateTime, relativeTime, shortId } from "@/lib/utils";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function useReport(runId: string | null) {
  return useQuery<unknown>({
    queryKey: ["report", runId],
    enabled: Boolean(runId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/runs/{run_id}/report", { params: { path: { run_id: runId ?? "" } } }),
      ),
    retry: 0,
    staleTime: 5 * 60_000,
  });
}

export function ReportsView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selected = searchParams.get("run");

  const runsQuery = useRuns({ limit: 50, state: "COMPLETED" });
  const runs = runsQuery.data?.runs ?? [];
  const report = useReport(selected);
  const runDetail = useRun(selected);
  const artifacts = runDetail.data?.artifacts ?? [];
  const record = isRecord(report.data) ? report.data : null;

  return (
    <div className="flex flex-col gap-2.5 p-4">
      <div className="flex items-center gap-3">
        <h1 className="flex items-center gap-1.5 text-[13px] font-semibold tracking-[0.04em]">
          <FileText size={14} className="text-info" aria-hidden />
          Reports
        </h1>
        <span className="mono text-[11px] text-dim">{runs.length} completed runs</span>
      </div>

      <div className="grid grid-cols-[360px_minmax(0,1fr)] gap-2">
        <Panel className="h-[calc(100vh-130px)]">
          <PanelHeader>
            <PanelTitle>Completed runs</PanelTitle>
          </PanelHeader>
          <PanelBody className="min-h-0 overflow-y-auto p-0">
            {runsQuery.isError ? (
              <ErrorState error={runsQuery.error} onRetry={() => void runsQuery.refetch()} />
            ) : runsQuery.isLoading ? (
              <SkeletonRows rows={8} className="p-3" />
            ) : runs.length === 0 ? (
              <EmptyState
                title="No completed run"
                description="A report is generated once a run completes and the analysis finishes."
                action={
                  <Button asChild variant="primary">
                    <Link href="/mission-control">Open Mission Control</Link>
                  </Button>
                }
              />
            ) : (
              <ul className="divide-y divide-border">
                {runs.map((run) => (
                  <li key={run.id}>
                    <button
                      type="button"
                      onClick={() => router.replace(`/reports?run=${run.id}`)}
                      className={cn(
                        "flex w-full flex-col gap-0.5 px-3 py-2 text-left transition-colors hover:bg-panel-2",
                        run.id === selected && "bg-info-soft",
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <span className="mono text-[11px] text-info">{shortId(run.id)}</span>
                        <span className="truncate text-[12px] text-foreground">
                          {run.scenario_name}
                        </span>
                        <ResultBadge result={run.result} size="xs" className="ml-auto" />
                      </span>
                      <span className="flex items-center gap-2 text-[10.5px] text-dim">
                        <span className="mono">score {formatScore(run.resilience_score)}</span>
                        <span className="mono">{run.adapter}</span>
                        <span className="ml-auto" title={run.created_at}>
                          {relativeTime(run.created_at)}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </PanelBody>
        </Panel>

        <Panel className="h-[calc(100vh-130px)]">
          <PanelHeader>
            <PanelTitle>Report</PanelTitle>
            {selected ? (
              <div className="ml-auto flex items-center gap-1.5">
                <Button asChild variant="ghost" size="xs">
                  <Link href={`/runs/${selected}`}>Run analysis</Link>
                </Button>
                <Button asChild variant="outline" size="xs">
                  <a
                    href={apiUrl(`/api/v1/runs/${selected}/artifacts/report.json`)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Download size={10} aria-hidden />
                    report.json
                  </a>
                </Button>
                <Button asChild variant="primary" size="xs">
                  <a
                    href={apiUrl(`/api/v1/runs/${selected}/report.html`)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open HTML report
                    <ExternalLink size={10} aria-hidden />
                  </a>
                </Button>
              </div>
            ) : null}
          </PanelHeader>
          <PanelBody className="min-h-0 overflow-y-auto p-0">
            {!selected ? (
              <EmptyState
                icon={FileText}
                title="Select a run"
                description="Pick a completed run on the left to read its canonical JSON report or open the standalone HTML report."
              />
            ) : report.isError ? (
              <ErrorState
                title="Report not ready"
                error={report.error}
                onRetry={() => void report.refetch()}
              />
            ) : report.isLoading ? (
              <LoadingPanel label="Loading report" />
            ) : !record ? (
              <EmptyState
                title="Unexpected report format"
                description="The report endpoint did not return a JSON object for this run."
              />
            ) : (
              <div className="flex flex-col">
                <ReportHeadline record={record} />
                <JsonSection
                  title="Summary"
                  value={record.summary}
                  defaultOpen
                  description="Headline figures generated from observed events"
                />
                <JsonSection
                  title="Score"
                  value={record.score}
                  description="Weighted dimensions and hard gates"
                />
                <JsonSection
                  title="Metrics"
                  value={record.metrics}
                  description="Every computed metric group"
                />
                <JsonSection
                  title="Assertions"
                  value={record.assertions}
                  description="Declared assertions and their outcome"
                />
                <JsonSection title="Scenario" value={record.scenario} />
                <JsonSection title="Target" value={record.target} />
                <JsonSection title="Provenance" value={record.provenance} />
                <JsonSection title="Subsystem timeline" value={record.subsystem_timeline} />
                <JsonSection title="Events" value={record.events} />
                <JsonSection title="Topology" value={record.topology} />

                <section className="border-t border-border">
                  <h3 className="panel-title px-3 py-1.5">Artifacts</h3>
                  {runDetail.isLoading ? (
                    <SkeletonRows rows={3} className="px-3 pb-3" />
                  ) : artifacts.length === 0 ? (
                    <p className="px-3 pb-3 text-[11.5px] text-muted">No artifact stored.</p>
                  ) : (
                    <ul className="flex flex-col divide-y divide-border">
                      {artifacts.map((artifact) => (
                        <li
                          key={artifact.name}
                          className="flex items-center gap-3 px-3 py-1.5 text-[11.5px]"
                        >
                          <span className="mono text-foreground">{artifact.name}</span>
                          <span className="text-muted">{artifact.description}</span>
                          <span className="mono ml-auto text-dim">
                            {formatBytes(artifact.size_bytes)}
                          </span>
                          <Button asChild variant="ghost" size="xs">
                            <a href={apiUrl(artifact.url)} target="_blank" rel="noreferrer">
                              <Download size={10} aria-hidden />
                              Download
                            </a>
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </div>
            )}
          </PanelBody>
        </Panel>
      </div>
    </div>
  );
}

function ReportHeadline({ record }: { record: Record<string, unknown> }) {
  const result = typeof record.result === "string" ? record.result : null;
  const score = typeof record.resilience_score === "number" ? record.resilience_score : null;
  const generatedAt = typeof record.generated_at === "string" ? record.generated_at : null;
  const schema = typeof record.schema_version === "string" ? record.schema_version : null;
  const scenario = isRecord(record.scenario) ? record.scenario : null;
  return (
    <div className="flex flex-wrap items-center gap-4 border-b border-border bg-panel-2 px-3 py-2">
      <span className="text-[13px] font-semibold text-foreground">
        {typeof scenario?.name === "string" ? scenario.name : "Report"}
      </span>
      {result ? (
        <ResultBadge
          result={result === "passed" || result === "failed" ? result : "inconclusive"}
          size="sm"
        />
      ) : null}
      {score !== null ? (
        <span className="mono text-[13px] text-foreground">{formatScore(score)}</span>
      ) : null}
      <span className="mono ml-auto text-[10.5px] text-dim">
        schema {schema ?? "unknown"} generated {formatDateTime(generatedAt)}
      </span>
    </div>
  );
}

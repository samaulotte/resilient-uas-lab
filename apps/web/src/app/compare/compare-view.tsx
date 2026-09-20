"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, GitCompareArrows } from "lucide-react";

import { RunPicker } from "@/components/compare/run-picker";
import { EventRow } from "@/components/mission/event-feed";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/feedback";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { InfoTip } from "@/components/ui/tooltip";
import { useRuns } from "@/hooks/use-runs";
import { api, unwrap } from "@/lib/api";
import {
  BETTER_LABEL,
  formatMetricDelta,
  formatMetricValue,
  VERDICT_LABEL,
  verdictTone,
  type ComparisonVerdict,
} from "@/lib/format";
import { TONE_TEXT } from "@/lib/states";
import { cn, shortId } from "@/lib/utils";
import type { CompareResponse } from "@reslab/api-client";

const VERDICT_SENTENCE: Record<ComparisonVerdict, string> = {
  improvement: "The candidate improved on the baseline.",
  regression: "The candidate regressed against the baseline.",
  unchanged: "No metric moved between the two runs.",
  changed: "Metrics moved without a preferred direction.",
  not_comparable: "These runs cannot be compared on equal terms.",
};

function useCompare(baseline: string | null, candidate: string | null) {
  return useQuery<CompareResponse>({
    queryKey: ["compare", baseline, candidate],
    enabled: Boolean(baseline && candidate),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/compare", {
          params: { query: { baseline: baseline ?? "", candidate: candidate ?? "" } },
        }),
      ),
    retry: 0,
  });
}

export function CompareView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const baseline = searchParams.get("baseline");
  const candidate = searchParams.get("candidate");

  const runsQuery = useRuns({ limit: 50, state: "COMPLETED" });
  const runs = useMemo(() => runsQuery.data?.runs ?? [], [runsQuery.data]);
  const comparison = useCompare(baseline, candidate);

  const select = (role: "baseline" | "candidate", runId: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set(role, runId);
    router.replace(`/compare?${params.toString()}`);
  };

  const data = comparison.data;

  return (
    <div className="flex flex-col gap-2.5 p-4">
      <div className="flex items-center gap-3">
        <h1 className="flex items-center gap-1.5 text-[13px] font-semibold tracking-[0.04em]">
          <GitCompareArrows size={14} className="text-info" aria-hidden />
          Compare runs
        </h1>
      </div>

      <Panel>
        <PanelBody className="grid grid-cols-[1fr_auto_1fr] items-end gap-3 p-3">
          <RunPicker
            label="Baseline"
            runs={runs}
            value={baseline}
            onChange={(id) => select("baseline", id)}
            emptyLabel="Select the reference run"
          />
          <ArrowRight size={14} className="mb-2 text-dim" aria-hidden />
          <RunPicker
            label="Candidate"
            runs={runs}
            value={candidate}
            onChange={(id) => select("candidate", id)}
            emptyLabel="Select the run under test"
          />
        </PanelBody>
      </Panel>

      {!baseline || !candidate ? (
        <Panel>
          <PanelBody>
            <EmptyState
              icon={GitCompareArrows}
              title="Pick two completed runs"
              description="A comparison needs a baseline and a candidate. Runs of the same scenario and the same content hash are the only ones that compare on strictly equal terms."
            />
          </PanelBody>
        </Panel>
      ) : comparison.isError ? (
        <Panel>
          <PanelBody>
            <ErrorState
              title="Comparison unavailable"
              error={comparison.error}
              onRetry={() => void comparison.refetch()}
            />
          </PanelBody>
        </Panel>
      ) : comparison.isLoading || !data ? (
        <SkeletonRows rows={10} />
      ) : (
        <>
          <section
            className={cn(
              "panel flex flex-wrap items-center gap-4 px-3 py-2.5",
              data.verdict === "improvement" && "border-ok/50",
              data.verdict === "regression" && "border-bad/50",
              data.verdict === "mixed" && "border-warn/50",
            )}
            aria-label="Comparison verdict"
          >
            <Badge
              tone={
                data.verdict === "improvement"
                  ? "ok"
                  : data.verdict === "regression"
                    ? "bad"
                    : data.verdict === "mixed"
                      ? "warn"
                      : "dim"
              }
              size="md"
            >
              {data.verdict.replace("_", " ").toUpperCase()}
            </Badge>
            <span className="text-[12px] text-foreground">
              {data.verdict === "mixed"
                ? "Some metrics improved while others regressed."
                : VERDICT_SENTENCE[data.verdict as ComparisonVerdict]}
            </span>
            <span className="mono text-[11.5px] text-ok">{data.improvements} improvements</span>
            <span className="mono text-[11.5px] text-bad">{data.regressions} regressions</span>
            <div className="ml-auto flex items-center gap-2">
              <Badge tone={data.same_scenario ? "ok" : "warn"} size="xs">
                {data.same_scenario ? "SAME SCENARIO" : "DIFFERENT SCENARIO"}
              </Badge>
              <Badge tone={data.same_scenario_hash ? "ok" : "warn"} size="xs">
                {data.same_scenario_hash ? "SAME DOCUMENT" : "DIFFERENT DOCUMENT"}
              </Badge>
              <InfoTip label="About comparability">
                Runs of a different scenario, or of a different version of the same document, do
                not measure the same thing. The verdict is reported but should be read with that in
                mind.
              </InfoTip>
            </div>
          </section>

          <div className="grid grid-cols-2 gap-2">
            {(
              [
                { role: "Baseline", run: data.baseline },
                { role: "Candidate", run: data.candidate },
              ] as const
            ).map(({ role, run }) => (
              <Panel key={role}>
                <PanelHeader>
                  <PanelTitle>{role}</PanelTitle>
                  <Link
                    href={`/runs/${run.id}`}
                    className="mono ml-auto text-[11px] text-info hover:underline"
                  >
                    {shortId(run.id)}
                  </Link>
                </PanelHeader>
                <PanelBody className="grid grid-cols-4 gap-2 p-2.5 text-[11.5px]">
                  <span className="text-muted">Scenario</span>
                  <span className="col-span-3 text-foreground">
                    {run.scenario_name} <span className="mono text-dim">v{run.scenario_version}</span>
                  </span>
                  <span className="text-muted">Adapter</span>
                  <span className="col-span-3 mono text-foreground">
                    {run.adapter}, seed {run.seed}, speed {run.speed}x
                  </span>
                  <span className="text-muted">Score</span>
                  <span className="col-span-3 mono text-foreground">
                    {run.resilience_score ?? "n/a"} ({run.result ?? "not analyzed"})
                  </span>
                </PanelBody>
              </Panel>
            ))}
          </div>

          <Panel>
            <PanelHeader>
              <PanelTitle>Metrics</PanelTitle>
              <span className="ml-auto text-[10px] text-dim">
                A neutral metric that moved is reported as changed, never as better or worse
              </span>
            </PanelHeader>
            <PanelBody className="p-0">
              <Table>
                <THead>
                  <tr>
                    <TH>Metric</TH>
                    <TH className="text-right">Baseline</TH>
                    <TH className="text-right">Candidate</TH>
                    <TH className="text-right">Delta</TH>
                    <TH>Verdict</TH>
                  </tr>
                </THead>
                <TBody>
                  {data.metrics.map((metric) => (
                    <TR key={metric.key}>
                      <TD>
                        <span className="flex items-center gap-1">
                          {metric.label}
                          <InfoTip label={`About ${metric.label}`}>
                            <span className="mono block text-info">{metric.key}</span>
                            <span className="mt-1 block text-muted">
                              {BETTER_LABEL[metric.better]}
                            </span>
                          </InfoTip>
                        </span>
                      </TD>
                      <TD className="mono text-right">
                        {formatMetricValue(metric.baseline, metric.unit)}
                      </TD>
                      <TD className="mono text-right">
                        {formatMetricValue(metric.candidate, metric.unit)}
                      </TD>
                      <TD
                        className={cn("mono text-right", TONE_TEXT[verdictTone(metric.verdict)])}
                      >
                        {formatMetricDelta(metric.delta, metric.unit)}
                      </TD>
                      <TD>
                        <Badge tone={verdictTone(metric.verdict)} size="xs">
                          {VERDICT_LABEL[metric.verdict]}
                        </Badge>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </PanelBody>
          </Panel>

          <div className="grid grid-cols-2 gap-2">
            <Panel>
              <PanelHeader>
                <PanelTitle>Score dimensions</PanelTitle>
                <span className="ml-auto text-[10px] text-dim">points contributed</span>
              </PanelHeader>
              <PanelBody className="p-0">
                <Table>
                  <THead>
                    <tr>
                      <TH>Dimension</TH>
                      <TH className="w-[190px]">Baseline vs candidate</TH>
                      <TH className="text-right">Delta</TH>
                      <TH>Verdict</TH>
                    </tr>
                  </THead>
                  <TBody>
                    {data.dimensions.map((dimension) => {
                      const max = Math.max(dimension.weight, 1);
                      const baselineValue = dimension.baseline ?? 0;
                      const candidateValue = dimension.candidate ?? 0;
                      return (
                        <TR key={dimension.dimension}>
                          <TD className="whitespace-nowrap">
                            {dimension.label}
                            <span className="mono ml-1 text-[10px] text-dim">
                              w{dimension.weight}
                            </span>
                          </TD>
                          <TD>
                            <div className="flex flex-col gap-1">
                              <div className="flex items-center gap-1.5">
                                <span className="w-[42px] text-[9.5px] text-dim">base</span>
                                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-panel-3">
                                  <div
                                    className="h-full rounded-full bg-dim"
                                    style={{ width: `${(baselineValue / max) * 100}%` }}
                                  />
                                </div>
                                <span className="mono w-[34px] text-right text-[10px] text-muted">
                                  {baselineValue.toFixed(1)}
                                </span>
                              </div>
                              <div className="flex items-center gap-1.5">
                                <span className="w-[42px] text-[9.5px] text-dim">cand</span>
                                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-panel-3">
                                  <div
                                    className={cn(
                                      "h-full rounded-full",
                                      dimension.verdict === "regression"
                                        ? "bg-bad"
                                        : dimension.verdict === "improvement"
                                          ? "bg-ok"
                                          : "bg-info",
                                    )}
                                    style={{ width: `${(candidateValue / max) * 100}%` }}
                                  />
                                </div>
                                <span className="mono w-[34px] text-right text-[10px] text-foreground">
                                  {candidateValue.toFixed(1)}
                                </span>
                              </div>
                            </div>
                          </TD>
                          <TD
                            className={cn(
                              "mono text-right",
                              TONE_TEXT[verdictTone(dimension.verdict)],
                            )}
                          >
                            {dimension.delta === null
                              ? "n/a"
                              : `${dimension.delta > 0 ? "+" : ""}${dimension.delta.toFixed(2)}`}
                          </TD>
                          <TD>
                            <Badge tone={verdictTone(dimension.verdict)} size="xs">
                              {VERDICT_LABEL[dimension.verdict]}
                            </Badge>
                          </TD>
                        </TR>
                      );
                    })}
                  </TBody>
                </Table>
              </PanelBody>
            </Panel>

            <Panel>
              <PanelHeader>
                <PanelTitle>Assertions</PanelTitle>
              </PanelHeader>
              <PanelBody className="p-0">
                {data.assertions.length === 0 ? (
                  <p className="px-3 py-4 text-[12px] text-muted">
                    Neither run evaluated an assertion.
                  </p>
                ) : (
                  <Table>
                    <THead>
                      <tr>
                        <TH>Expression</TH>
                        <TH>Severity</TH>
                        <TH>Baseline</TH>
                        <TH>Candidate</TH>
                        <TH>Verdict</TH>
                      </tr>
                    </THead>
                    <TBody>
                      {data.assertions.map((assertion, index) => (
                        <TR key={`${assertion.expression}-${index}`}>
                          <TD className="mono">{assertion.expression}</TD>
                          <TD className="text-muted">{assertion.severity}</TD>
                          <TD className="mono text-muted">{assertion.baseline ?? "n/a"}</TD>
                          <TD className="mono text-foreground">{assertion.candidate ?? "n/a"}</TD>
                          <TD>
                            <Badge tone={verdictTone(assertion.verdict)} size="xs">
                              {VERDICT_LABEL[assertion.verdict]}
                            </Badge>
                          </TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                )}
              </PanelBody>
            </Panel>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {(
              [
                { role: "Baseline events", events: data.baseline_events },
                { role: "Candidate events", events: data.candidate_events },
              ] as const
            ).map(({ role, events }) => (
              <Panel key={role}>
                <PanelHeader>
                  <PanelTitle>{role}</PanelTitle>
                  <span className="ml-auto text-[10px] text-dim">{events.length} events</span>
                </PanelHeader>
                <PanelBody className="max-h-[420px] overflow-y-auto p-0">
                  {events.length === 0 ? (
                    <p className="px-3 py-4 text-[12px] text-muted">No event recorded.</p>
                  ) : (
                    <ul className="flex flex-col divide-y divide-border/70">
                      {events.map((event) => (
                        <EventRow
                          key={`${role}-${event.sequence}`}
                          event={event}
                          dense
                        />
                      ))}
                    </ul>
                  )}
                </PanelBody>
              </Panel>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

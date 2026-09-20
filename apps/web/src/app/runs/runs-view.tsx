"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { History } from "lucide-react";

import { ResultBadge, RunStateBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/feedback";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useRuns } from "@/hooks/use-runs";
import { useScenarios } from "@/hooks/use-scenarios";
import { useSystemInfo } from "@/hooks/use-system";
import { formatScore } from "@/lib/format";
import { formatDuration, relativeTime, shortId } from "@/lib/utils";
import type { RunState } from "@reslab/api-client";

const RUN_STATES: readonly RunState[] = [
  "CREATED",
  "VALIDATING",
  "QUEUED",
  "PREPARING",
  "RUNNING",
  "RECOVERING",
  "COLLECTING",
  "ANALYZING",
  "COMPLETED",
  "FAILED",
  "CANCELLED",
];

const RESULTS = ["passed", "failed", "inconclusive"] as const;
const ANY = "__any__";
const PAGE_SIZE = 25;

export function RunsView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const system = useSystemInfo();
  const scenarios = useScenarios();

  const [state, setState] = useState<string>(searchParams.get("state") ?? ANY);
  const [scenario, setScenario] = useState<string>(searchParams.get("scenario") ?? ANY);
  const [adapter, setAdapter] = useState<string>(searchParams.get("adapter") ?? ANY);
  const [result, setResult] = useState<string>(searchParams.get("result") ?? ANY);
  const [offset, setOffset] = useState(0);

  const query = useRuns({
    limit: PAGE_SIZE,
    offset,
    state: state === ANY ? null : (state as RunState),
    scenario: scenario === ANY ? null : scenario,
    adapter: adapter === ANY ? null : adapter,
    result: result === ANY ? null : result,
  });

  const runs = query.data?.runs ?? [];
  const total = query.data?.total ?? 0;
  const filtered = state !== ANY || scenario !== ANY || adapter !== ANY || result !== ANY;

  const resetFilters = () => {
    setState(ANY);
    setScenario(ANY);
    setAdapter(ANY);
    setResult(ANY);
    setOffset(0);
  };

  return (
    <div className="flex flex-col gap-2.5 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="flex items-center gap-1.5 text-[13px] font-semibold tracking-[0.04em]">
          <History size={14} className="text-info" aria-hidden />
          Runs
        </h1>
        <span className="mono text-[11px] text-dim">{total} total</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <FilterSelect
            label="State"
            value={state}
            onChange={(value) => {
              setState(value);
              setOffset(0);
            }}
            options={RUN_STATES.map((entry) => ({ value: entry, label: entry }))}
          />
          <FilterSelect
            label="Scenario"
            value={scenario}
            onChange={(value) => {
              setScenario(value);
              setOffset(0);
            }}
            options={(scenarios.data ?? []).map((entry) => ({
              value: entry.name,
              label: entry.name,
            }))}
          />
          <FilterSelect
            label="Adapter"
            value={adapter}
            onChange={(value) => {
              setAdapter(value);
              setOffset(0);
            }}
            options={(system.data?.adapters ?? []).map((entry) => ({
              value: entry.name,
              label: entry.display_name,
            }))}
          />
          <FilterSelect
            label="Result"
            value={result}
            onChange={(value) => {
              setResult(value);
              setOffset(0);
            }}
            options={RESULTS.map((entry) => ({ value: entry, label: entry }))}
          />
          {filtered ? (
            <Button variant="ghost" onClick={resetFilters}>
              Clear
            </Button>
          ) : null}
        </div>
      </div>

      <Panel>
        <PanelHeader>
          <PanelTitle>Run history</PanelTitle>
          <span className="ml-auto text-[10px] text-dim">
            {total === 0 ? "0" : `${offset + 1} to ${Math.min(offset + PAGE_SIZE, total)}`} of{" "}
            {total}
          </span>
        </PanelHeader>
        <PanelBody className="p-0">
          {query.isError ? (
            <ErrorState error={query.error} onRetry={() => void query.refetch()} />
          ) : query.isLoading ? (
            <SkeletonRows rows={8} className="p-3" />
          ) : runs.length === 0 ? (
            <EmptyState
              title={filtered ? "No run matches these filters" : "No run recorded yet"}
              description={
                filtered
                  ? "Relax a filter to see more runs."
                  : "Queue a scenario from the library or run the demo from Mission Control."
              }
              action={
                filtered ? (
                  <Button variant="outline" onClick={resetFilters}>
                    Clear filters
                  </Button>
                ) : (
                  <Button asChild variant="primary">
                    <Link href="/scenarios">Open the scenario library</Link>
                  </Button>
                )
              }
            />
          ) : (
            <Table>
              <THead>
                <tr>
                  <TH>Run</TH>
                  <TH>Scenario</TH>
                  <TH>Adapter</TH>
                  <TH>State</TH>
                  <TH>Result</TH>
                  <TH className="text-right">Score</TH>
                  <TH className="text-right">Sim. duration</TH>
                  <TH>Created</TH>
                  <TH>Label</TH>
                  <TH className="text-right">Actions</TH>
                </tr>
              </THead>
              <TBody>
                {runs.map((run) => (
                  <TR key={run.id}>
                    <TD>
                      <Link
                        href={`/runs/${run.id}`}
                        className="mono text-info hover:underline"
                        title={run.id}
                      >
                        {shortId(run.id)}
                      </Link>
                    </TD>
                    <TD>
                      <Link href={`/scenarios/${run.scenario_name}`} className="hover:underline">
                        {run.scenario_name}
                      </Link>
                      <span className="mono ml-1 text-[10px] text-dim">
                        v{run.scenario_version}
                      </span>
                    </TD>
                    <TD className="text-muted">{run.adapter}</TD>
                    <TD>
                      <RunStateBadge state={run.state} size="xs" />
                    </TD>
                    <TD>
                      <ResultBadge result={run.result} size="xs" />
                    </TD>
                    <TD className="mono text-right">{formatScore(run.resilience_score)}</TD>
                    <TD className="mono text-right text-muted">
                      {formatDuration(run.last_simulation_time)}
                    </TD>
                    <TD className="text-muted" title={run.created_at}>
                      {relativeTime(run.created_at)}
                    </TD>
                    <TD className="max-w-[140px] truncate text-muted">{run.label || "-"}</TD>
                    <TD>
                      <div className="flex items-center justify-end gap-1">
                        <Button asChild variant="ghost" size="xs">
                          <Link href={`/mission-control?run=${run.id}`}>Mission Control</Link>
                        </Button>
                        {run.state === "COMPLETED" ? (
                          <>
                            <Button asChild variant="ghost" size="xs">
                              <Link href={`/reports?run=${run.id}`}>Report</Link>
                            </Button>
                            <Button
                              variant="ghost"
                              size="xs"
                              title="Use as comparison baseline"
                              onClick={() => router.push(`/compare?baseline=${run.id}`)}
                            >
                              Baseline
                            </Button>
                            <Button
                              variant="ghost"
                              size="xs"
                              title="Use as comparison candidate"
                              onClick={() => router.push(`/compare?candidate=${run.id}`)}
                            >
                              Candidate
                            </Button>
                          </>
                        ) : null}
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </PanelBody>
      </Panel>

      {total > PAGE_SIZE ? (
        <div className="flex items-center justify-end gap-2">
          <Button
            variant="outline"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly { value: string; label: string }[];
}) {
  return (
    <label className="flex items-center gap-1.5">
      <span className="panel-title text-[9px]">{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger aria-label={label} className="h-6 w-[148px] text-[11.5px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any</SelectItem>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}

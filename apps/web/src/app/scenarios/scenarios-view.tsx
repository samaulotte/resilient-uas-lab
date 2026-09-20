"use client";

import Link from "next/link";
import { LayoutList, Play, Plus } from "lucide-react";

import { RunScenarioDialog } from "@/components/runs/run-scenario-dialog";
import { Badge, ResultBadge, RunStateBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, SkeletonRows } from "@/components/ui/feedback";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { useScenarios } from "@/hooks/use-scenarios";
import { useSystemInfo } from "@/hooks/use-system";
import { formatScore } from "@/lib/format";
import { relativeTime, shortId } from "@/lib/utils";

export function ScenariosView() {
  const system = useSystemInfo();
  const scenarios = useScenarios();
  const adapters = system.data?.adapters ?? [];

  return (
    <div className="flex flex-col gap-2.5 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="flex items-center gap-1.5 text-[13px] font-semibold tracking-[0.04em]">
          <LayoutList size={14} className="text-info" aria-hidden />
          Scenario library
        </h1>
        <span className="mono text-[11px] text-dim">{scenarios.data?.length ?? 0} scenarios</span>
        <Button asChild variant="primary" size="sm" className="ml-auto">
          <Link href="/scenarios/new">
            <Plus size={12} aria-hidden />
            New scenario
          </Link>
        </Button>
      </div>

      <Panel>
        <PanelHeader>
          <PanelTitle>Scenarios</PanelTitle>
          <span className="ml-auto text-[10px] text-dim">
            A scenario declares subsystems, effects, times and expectations, never commands
          </span>
        </PanelHeader>
        <PanelBody className="p-0">
          {scenarios.isError ? (
            <ErrorState error={scenarios.error} onRetry={() => void scenarios.refetch()} />
          ) : scenarios.isLoading ? (
            <SkeletonRows rows={6} className="p-3" />
          ) : (scenarios.data ?? []).length === 0 ? (
            <EmptyState
              title="The library is empty"
              description="Author a scenario in the studio and save it to the library."
              action={
                <Button asChild variant="primary">
                  <Link href="/scenarios/new">New scenario</Link>
                </Button>
              }
            />
          ) : (
            <Table>
              <THead>
                <tr>
                  <TH>Name</TH>
                  <TH>Description</TH>
                  <TH>Adapter</TH>
                  <TH>Tags</TH>
                  <TH className="text-right">Events</TH>
                  <TH className="text-right">Assertions</TH>
                  <TH>Last run</TH>
                  <TH>Updated</TH>
                  <TH className="text-right">Actions</TH>
                </tr>
              </THead>
              <TBody>
                {(scenarios.data ?? []).map((scenario) => (
                  <TR key={scenario.name}>
                    <TD>
                      <Link
                        href={`/scenarios/${scenario.name}`}
                        className="mono text-info hover:underline"
                      >
                        {scenario.name}
                      </Link>
                      <span className="mono ml-1 text-[10px] text-dim">v{scenario.version}</span>
                    </TD>
                    <TD className="max-w-[420px] text-muted">
                      <span className="line-clamp-2">{scenario.description}</span>
                    </TD>
                    <TD className="mono text-muted">{scenario.adapter}</TD>
                    <TD>
                      <div className="flex flex-wrap gap-1">
                        {scenario.tags.map((tag) => (
                          <Badge key={tag} tone="dim" size="xs">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    </TD>
                    <TD className="mono text-right">{scenario.event_count}</TD>
                    <TD className="mono text-right">{scenario.assertion_count}</TD>
                    <TD>
                      {scenario.last_run ? (
                        <span className="flex items-center gap-1.5">
                          <Link
                            href={`/runs/${scenario.last_run.id}`}
                            className="mono text-info hover:underline"
                          >
                            {shortId(scenario.last_run.id)}
                          </Link>
                          <RunStateBadge state={scenario.last_run.state} size="xs" />
                          <ResultBadge result={scenario.last_run.result} size="xs" />
                          <span className="mono text-[11px] text-muted">
                            {formatScore(scenario.last_run.resilience_score)}
                          </span>
                        </span>
                      ) : (
                        <span className="text-dim">never run</span>
                      )}
                    </TD>
                    <TD className="text-muted" title={scenario.updated_at}>
                      {relativeTime(scenario.updated_at)}
                    </TD>
                    <TD>
                      <div className="flex items-center justify-end gap-1">
                        <RunScenarioDialog
                          trigger={
                            <Button variant="primary" size="xs">
                              <Play size={10} aria-hidden />
                              Run
                            </Button>
                          }
                          scenarioName={scenario.name}
                          adapters={adapters}
                          defaultAdapter={scenario.adapter}
                          title={`Run ${scenario.name}`}
                        />
                        <Button asChild variant="ghost" size="xs">
                          <Link href={`/scenarios/${scenario.name}`}>Open</Link>
                        </Button>
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </PanelBody>
      </Panel>
    </div>
  );
}

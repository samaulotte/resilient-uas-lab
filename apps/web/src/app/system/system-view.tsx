"use client";

import { AlertTriangle, Network } from "lucide-react";

import { TopologyGraph } from "@/components/system/topology-graph";
import { Badge, ComponentStateBadge } from "@/components/ui/badge";
import { ErrorState, SkeletonRows } from "@/components/ui/feedback";
import { Field, Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useSystemInfo } from "@/hooks/use-system";
import { DOMAIN_LABEL } from "@/lib/states";
import { cn, relativeTime } from "@/lib/utils";
import type { Domain } from "@reslab/api-client";

const ADAPTER_STATUS_TONE = {
  available: "ok",
  experimental: "warn",
  planned: "dim",
} as const;

export function SystemView() {
  const query = useSystemInfo();
  const system = query.data;

  if (query.isError) {
    return (
      <div className="p-4">
        <ErrorState
          title="Platform unavailable"
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      </div>
    );
  }

  if (!system) {
    return <SkeletonRows rows={12} className="p-4" />;
  }

  const healthy = system.health.database && system.health.bus && system.health.artifact_store;

  return (
    <div className="flex flex-col gap-2.5 p-4">
      <div className="flex items-center gap-3">
        <h1 className="flex items-center gap-1.5 text-[13px] font-semibold tracking-[0.04em]">
          <Network size={14} className="text-info" aria-hidden />
          System
        </h1>
        <Badge tone={healthy ? "ok" : "bad"} size="xs">
          {healthy ? "PLATFORM HEALTHY" : "PLATFORM DEGRADED"}
        </Badge>
        <span className="mono text-[11px] text-dim">{system.environment}</span>
      </div>

      <div className="grid grid-cols-[1.4fr_1fr_1fr] gap-2">
        <Panel>
          <PanelHeader>
            <PanelTitle>Versions</PanelTitle>
          </PanelHeader>
          <PanelBody className="grid grid-cols-3 gap-x-4 gap-y-2 p-3">
            <Field label="Software">
              <span className="mono">{system.software_version}</span>
            </Field>
            <Field label="Scenario API">
              <span className="mono">{system.scenario_api_version}</span>
            </Field>
            <Field label="Report schema">
              <span className="mono">{system.report_schema_version}</span>
            </Field>
            <Field label="Stream protocol">
              <span className="mono">{system.protocol_version}</span>
            </Field>
            <Field label="Git commit">
              <span className="mono">{system.git_commit ?? "not recorded"}</span>
            </Field>
            <Field label="Environment">
              <span className="mono">{system.environment}</span>
            </Field>
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader>
            <PanelTitle>Component health</PanelTitle>
          </PanelHeader>
          <PanelBody className="flex flex-col gap-1.5 p-3">
            {(
              [
                ["Database", system.health.database],
                ["Message bus", system.health.bus],
                ["Artifact store", system.health.artifact_store],
              ] as const
            ).map(([label, ok]) => (
              <div key={label} className="flex items-center justify-between text-[12px]">
                <span className="text-muted">{label}</span>
                <Badge tone={ok ? "ok" : "bad"} size="xs">
                  {ok ? "READY" : "UNAVAILABLE"}
                </Badge>
              </div>
            ))}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader>
            <PanelTitle>Counts</PanelTitle>
          </PanelHeader>
          <PanelBody className="grid grid-cols-2 gap-x-4 gap-y-1 p-3">
            {Object.entries(system.counts).map(([key, value]) => (
              <div key={key} className="flex items-center justify-between text-[12px]">
                <span className="text-muted">{key.replace(/_/g, " ")}</span>
                <span className="mono text-foreground">{value}</span>
              </div>
            ))}
          </PanelBody>
        </Panel>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Panel>
          <PanelHeader>
            <PanelTitle>Adapters</PanelTitle>
            <span className="ml-auto text-[10px] text-dim">
              An adapter declares where the data comes from
            </span>
          </PanelHeader>
          <PanelBody className="p-0">
            <Table>
              <THead>
                <tr>
                  <TH>Adapter</TH>
                  <TH>Kind</TH>
                  <TH>Status</TH>
                  <TH>Data origin</TH>
                  <TH>Runners</TH>
                </tr>
              </THead>
              <TBody>
                {system.adapters.map((adapter) => (
                  <TR key={adapter.name}>
                    <TD>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span tabIndex={0} className="text-foreground">
                            {adapter.display_name}
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>
                          <span className="block">{adapter.description}</span>
                          {adapter.requirements ? (
                            <span className="mt-1 block text-muted">
                              Requires: {adapter.requirements}
                            </span>
                          ) : null}
                        </TooltipContent>
                      </Tooltip>
                      <span className="mono ml-1 text-[10px] text-dim">{adapter.name}</span>
                    </TD>
                    <TD className="text-muted">{adapter.kind}</TD>
                    <TD>
                      <span className="flex items-center gap-1.5">
                        <Badge tone={ADAPTER_STATUS_TONE[adapter.status]} size="xs">
                          {adapter.status.toUpperCase()}
                        </Badge>
                        <Badge tone={adapter.online ? "ok" : "dim"} size="xs">
                          {adapter.online ? "ONLINE" : "OFFLINE"}
                        </Badge>
                      </span>
                    </TD>
                    <TD className="text-muted">{adapter.data_origin}</TD>
                    <TD className="mono text-muted">
                      {adapter.runners.length > 0 ? adapter.runners.join(", ") : "none"}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader>
            <PanelTitle>Runners</PanelTitle>
          </PanelHeader>
          <PanelBody className="p-0">
            {system.runners.length === 0 ? (
              <p className="px-3 py-4 text-[12px] text-muted">
                No runner has registered. Queued runs will wait until one comes online.
              </p>
            ) : (
              <Table>
                <THead>
                  <tr>
                    <TH>Runner</TH>
                    <TH>Version</TH>
                    <TH>Adapters</TH>
                    <TH>Active run</TH>
                    <TH>Last heartbeat</TH>
                    <TH>State</TH>
                  </tr>
                </THead>
                <TBody>
                  {system.runners.map((runner) => (
                    <TR key={runner.runner_id}>
                      <TD className="mono">{runner.runner_id}</TD>
                      <TD className="mono text-muted">{runner.version}</TD>
                      <TD className="mono text-muted">{runner.adapters.join(", ")}</TD>
                      <TD className="mono text-muted">{runner.active_run_id ?? "idle"}</TD>
                      <TD className="text-muted" title={runner.last_heartbeat_at}>
                        {relativeTime(runner.last_heartbeat_at)}
                      </TD>
                      <TD>
                        <Badge tone={runner.online ? "ok" : "bad"} size="xs">
                          {runner.online ? "ONLINE" : "STALE"}
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

      <Panel>
        <PanelHeader>
          <PanelTitle>Topology</PanelTitle>
          <span className="ml-auto text-[10px] text-dim">
            {system.topology.name}, {system.topology.components.length} components,{" "}
            {system.topology.dependencies.length} dependencies
          </span>
        </PanelHeader>
        <PanelBody className="p-3">
          <TopologyGraph topology={system.topology} />
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-2 gap-2">
        <Panel>
          <PanelHeader>
            <PanelTitle>Trust boundaries</PanelTitle>
          </PanelHeader>
          <PanelBody className="flex flex-col gap-2 p-3">
            {system.topology.trust_boundaries.map((boundary) => (
              <div key={boundary.id} className="rounded-sm border border-info/40 bg-info-soft p-2">
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-medium text-foreground">{boundary.name}</span>
                  <span className="mono text-[10px] text-info">
                    {boundary.upstream_zone} to {boundary.downstream_zone}
                  </span>
                </div>
                {boundary.enforcement_point ? (
                  <p className="mono mt-0.5 text-[10.5px] text-info">
                    enforcement point {boundary.enforcement_point}
                  </p>
                ) : null}
                <p className="mt-1 text-[11.5px] leading-snug text-muted">{boundary.description}</p>
              </div>
            ))}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader>
            <PanelTitle>Score profiles</PanelTitle>
          </PanelHeader>
          <PanelBody className="flex flex-col gap-3 p-3">
            {system.score_profiles.map((profile) => {
              const total = Object.values(profile.weights).reduce((sum, value) => sum + value, 0);
              return (
                <div key={profile.name} className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-2">
                    <span className="mono text-[12px] text-foreground">{profile.name}</span>
                    <Badge tone={total === 100 ? "ok" : "bad"} size="xs">
                      weights sum {total}
                    </Badge>
                  </div>
                  <p className="text-[11.5px] leading-snug text-muted">{profile.description}</p>
                  <ul className="grid grid-cols-4 gap-x-3 gap-y-0.5">
                    {Object.entries(profile.weights)
                      .sort(([, a], [, b]) => b - a)
                      .map(([dimension, weight]) => (
                        <li
                          key={dimension}
                          className={cn(
                            "flex items-center justify-between text-[11px]",
                            weight === 0 && "opacity-50",
                          )}
                        >
                          <span className="truncate text-muted">
                            {dimension.replace(/_/g, " ")}
                          </span>
                          <span className="mono text-foreground">{weight}</span>
                        </li>
                      ))}
                  </ul>
                  {profile.parameters ? (
                    <p className="mono text-[10.5px] text-dim">
                      mttr target {profile.parameters.mttr_target}s, limit{" "}
                      {profile.parameters.mttr_limit}s, containment penalty{" "}
                      {profile.parameters.containment_penalty_per_domain} per domain
                    </p>
                  ) : null}
                </div>
              );
            })}
          </PanelBody>
        </Panel>
      </div>

      <Panel>
        <PanelHeader>
          <PanelTitle>Fault catalog</PanelTitle>
          <span className="ml-auto text-[10px] text-dim">
            The authoritative whitelist of effects per subsystem
          </span>
        </PanelHeader>
        <PanelBody className="p-0">
          <Table>
            <THead>
              <tr>
                <TH>Subsystem</TH>
                <TH>Domain</TH>
                <TH>Category</TH>
                <TH>Trust zone</TH>
                <TH>Healthy state</TH>
                <TH>Allowed effects</TH>
              </tr>
            </THead>
            <TBody>
              {system.catalog.map((entry) => (
                <TR key={entry.subsystem}>
                  <TD>
                    <span className="flex items-center gap-1.5">
                      {entry.critical ? (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span tabIndex={0} className="text-warn">
                              <AlertTriangle size={11} aria-hidden />
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>
                            Flight critical: losing this component means losing the flight-critical
                            function.
                          </TooltipContent>
                        </Tooltip>
                      ) : null}
                      <span className="text-foreground">{entry.name}</span>
                      <span className="mono text-[10px] text-dim">{entry.subsystem}</span>
                    </span>
                  </TD>
                  <TD className="text-muted">
                    {DOMAIN_LABEL[entry.domain as Domain] ?? entry.domain}
                  </TD>
                  <TD className="text-muted">{entry.category}</TD>
                  <TD className="mono text-muted">{entry.trust_zone}</TD>
                  <TD>
                    <ComponentStateBadge state={entry.healthy_state} size="xs" />
                  </TD>
                  <TD>
                    <div className="flex flex-wrap gap-1">
                      {entry.effects.length === 0 ? (
                        <span className="text-dim">none</span>
                      ) : (
                        entry.effects.map((effect) => (
                          <span
                            key={effect}
                            className="mono rounded-sm border border-border-strong px-1 py-[1px] text-[10px] text-muted"
                          >
                            {effect}
                          </span>
                        ))
                      )}
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Effect descriptors</PanelTitle>
          <span className="ml-auto text-[10px] text-dim">
            An effect describes what the target experiences, never how it is produced
          </span>
        </PanelHeader>
        <PanelBody className="p-0">
          <Table>
            <THead>
              <tr>
                <TH>Effect</TH>
                <TH>Description</TH>
                <TH>Transient</TH>
                <TH>Duration required</TH>
                <TH>Parameters</TH>
              </tr>
            </THead>
            <TBody>
              {system.effects.map((effect) => (
                <TR key={effect.effect}>
                  <TD className="mono">{effect.effect}</TD>
                  <TD className="text-muted">{effect.description}</TD>
                  <TD>
                    <Badge tone={effect.transient ? "info" : "dim"} size="xs">
                      {effect.transient ? "TRANSIENT" : "PERSISTENT"}
                    </Badge>
                  </TD>
                  <TD className="text-muted">{effect.duration_required ? "yes" : "no"}</TD>
                  <TD className="text-muted">
                    {effect.parameters.length === 0
                      ? "none"
                      : effect.parameters
                          .map((parameter) => {
                            const bounds = [
                              parameter.minimum !== null && parameter.minimum !== undefined
                                ? `min ${parameter.minimum}`
                                : null,
                              parameter.maximum !== null && parameter.maximum !== undefined
                                ? `max ${parameter.maximum}`
                                : null,
                            ]
                              .filter(Boolean)
                              .join(", ");
                            return `${parameter.name} (${parameter.type}${bounds ? `, ${bounds}` : ""})`;
                          })
                          .join("  |  ")}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </PanelBody>
      </Panel>
    </div>
  );
}

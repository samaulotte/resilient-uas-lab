"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo } from "react";
import { Play, Radar } from "lucide-react";

import { BlastRadius } from "@/components/mission/blast-radius";
import { ActiveAlerts, EventFeed, EventLegend } from "@/components/mission/event-feed";
import {
  ContainmentKpi,
  MissionKpi,
  RecoveryKpi,
  ScoreKpi,
} from "@/components/mission/kpi-row";
import { StateTimeline } from "@/components/mission/state-timeline";
import { StatusBar } from "@/components/mission/status-bar";
import { SystemPanel } from "@/components/mission/system-panel";
import { UpcomingInjections } from "@/components/mission/upcoming-injections";
import { DigitalTwin } from "@/components/twin/digital-twin";
import type { TwinFeed } from "@/components/twin/feed";
import { Badge, RunStateBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingPanel, Notice } from "@/components/ui/feedback";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Segmented } from "@/components/ui/segmented";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useRunStream } from "@/hooks/use-run-stream";
import { useLiveRunThrottled } from "@/hooks/use-live-view";
import {
  useCancelRun,
  useCreateRun,
  useRunEvents,
  useRunMetrics,
  useRunTelemetry,
  useRuns,
} from "@/hooks/use-runs";
import { useScenarios } from "@/hooks/use-scenarios";
import { useSystemInfo } from "@/hooks/use-system";
import { activeAlerts } from "@/lib/events";
import { safeParseScenarioDocument, scenarioSchedule } from "@/lib/scenario-document";
import {
  buildTimeline,
  currentHealth,
  injectionMarkers,
  liveContainmentKpis,
  liveMissionKpis,
  liveRecoveryKpis,
} from "@/lib/run-view";
import { ACTIVE_RUN_STATES } from "@/lib/states";
import { componentMap, componentNameMap, groupByDomain, missionFlightBoundary } from "@/lib/topology";
import { shortId } from "@/lib/utils";
import { useLiveRun } from "@/stores/live-run";
import { DEMO_SPEEDS, useSettings, type DemoSpeed } from "@/stores/settings";
import { isTerminalRunState, type RunSummary } from "@reslab/api-client";

const DEMO_SCENARIO = "compound-degradation";
const FEED_LIMIT = 150;

const SPEED_OPTIONS = DEMO_SPEEDS.map((speed) => ({
  value: String(speed),
  label: `${speed}x`,
  title: `Run the demo at ${speed} times real time`,
}));

function pickRun(runs: readonly RunSummary[]): RunSummary | undefined {
  const active = runs.find((run) => ACTIVE_RUN_STATES.includes(run.state));
  if (active) return active;
  const completed = runs.find((run) => run.state === "COMPLETED");
  return completed ?? runs[0];
}

export function MissionControlView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const runParam = searchParams.get("run");

  const system = useSystemInfo();
  const scenarios = useScenarios();
  const runsQuery = useRuns({ limit: 20 });
  const createRun = useCreateRun();
  const cancelRun = useCancelRun();

  const demoSpeed = useSettings((state) => state.demoSpeed);
  const setDemoSpeed = useSettings((state) => state.setDemoSpeed);
  const cameraMode = useSettings((state) => state.cameraMode);
  const setCameraMode = useSettings((state) => state.setCameraMode);
  const showLogEvents = useSettings((state) => state.showLogEvents);
  const reducedMotion = useSettings((state) => state.reducedMotion);

  const runs = useMemo(() => runsQuery.data?.runs ?? [], [runsQuery.data]);
  const selectedRunId = runParam ?? pickRun(runs)?.id ?? null;

  useRunStream(selectedRunId);

  const run = useLiveRun((state) => state.run);
  const events = useLiveRun((state) => state.events);
  const connection = useLiveRun((state) => state.status);
  const streamError = useLiveRun((state) => state.error);
  const finished = useLiveRun((state) => state.finished);
  const reportAvailable = useLiveRun((state) => state.reportAvailable);
  const plannedPath = useLiveRun((state) => state.plannedPath);
  const latest = useLiveRunThrottled((state) => state.latest, 400);
  const simulationTime = useLiveRunThrottled((state) => state.simulationTime, 400);

  const terminal = run ? isTerminalRunState(run.state) : false;
  const historyEnabled = Boolean(selectedRunId) && (terminal || finished);
  const telemetryQuery = useRunTelemetry(selectedRunId, historyEnabled);
  const eventsQuery = useRunEvents(selectedRunId, historyEnabled);
  const metricsQuery = useRunMetrics(selectedRunId, historyEnabled && run?.state === "COMPLETED");

  const telemetryData = telemetryQuery.data;
  const eventsData = eventsQuery.data;
  useEffect(() => {
    if (!telemetryData && !eventsData) return;
    useLiveRun.getState().replaceHistory({
      ...(telemetryData ? { samples: telemetryData.samples } : {}),
      ...(eventsData ? { events: eventsData.events } : {}),
    });
  }, [telemetryData, eventsData]);

  const feed = useMemo<TwinFeed>(
    () => ({
      getSample: () => useLiveRun.getState().latest,
      getTrail: () => useLiveRun.getState().samples,
      getGeneration: () => useLiveRun.getState().generation,
    }),
    [],
  );

  const topology = system.data?.topology;
  const components = useMemo(() => componentMap(topology), [topology]);
  const names = useMemo(() => componentNameMap(topology), [topology]);
  const groups = useMemo(() => groupByDomain(topology), [topology]);
  const boundary = useMemo(() => missionFlightBoundary(topology), [topology]);
  const adapter = system.data?.adapters.find((entry) => entry.name === run?.adapter);

  const health = useMemo(() => currentHealth(latest, events), [latest, events]);
  const alerts = useMemo(() => activeAlerts(latest, names), [latest, names]);
  // The flight core gets a track as soon as telemetry reports it: without an
  // observation there is nothing to claim about it.
  const tracks = useMemo(
    () =>
      buildTimeline(
        events,
        components,
        Math.max(simulationTime, 1),
        latest ? ["flight_control.core"] : [],
      ),
    [events, components, simulationTime, latest],
  );
  const markers = useMemo(() => injectionMarkers(events), [events]);
  const mission = useMemo(() => liveMissionKpis(latest, events), [latest, events]);
  const recovery = useMemo(() => liveRecoveryKpis(events), [events]);
  const containment = useMemo(() => liveContainmentKpis(events, components), [events, components]);

  const schedule = useMemo(() => {
    const draft = safeParseScenarioDocument(run?.scenario_document);
    return draft ? scenarioSchedule(draft) : [];
  }, [run?.scenario_document]);
  const appliedIds = useMemo(
    () =>
      new Set(
        events
          .filter((event) => event.kind === "INJECTION_APPLIED" && event.scenario_event_id)
          .map((event) => event.scenario_event_id ?? ""),
      ),
    [events],
  );

  const feedEvents = useMemo(() => {
    const filtered = showLogEvents ? events : events.filter((event) => event.kind !== "LOG");
    return [...filtered].reverse().slice(0, FEED_LIMIT);
  }, [events, showLogEvents]);

  const demoAvailable = (scenarios.data ?? []).some((entry) => entry.name === DEMO_SCENARIO);
  const mockOnline = system.data?.adapters.find((entry) => entry.name === "mock")?.online ?? false;
  const runnerOnline = (system.data?.runners ?? []).some((runner) => runner.online);

  const startDemo = () => {
    createRun.mutate(
      { scenario_name: DEMO_SCENARIO, adapter: "mock", speed: demoSpeed, label: "demo" },
      { onSuccess: (created) => router.push(`/mission-control?run=${created.id}`) },
    );
  };

  const toolbar = (
    <div className="flex flex-wrap items-center gap-3">
      <h1 className="flex items-center gap-1.5 text-[13px] font-semibold tracking-[0.04em] text-foreground">
        <Radar size={14} className="text-info" aria-hidden />
        Mission Control
      </h1>
      {runs.length > 0 ? (
        <div className="flex items-center gap-1.5">
          <span className="panel-title text-[9px]">Run</span>
          <Select
            value={selectedRunId ?? ""}
            onValueChange={(value) => router.push(`/mission-control?run=${value}`)}
          >
            <SelectTrigger aria-label="Select run" className="h-7 min-w-[360px] text-[11.5px]">
              <SelectValue placeholder="Select a run" className="min-w-0" />
            </SelectTrigger>
            <SelectContent>
              {runs.map((entry) => (
                <SelectItem
                  key={entry.id}
                  value={entry.id}
                  textValue={`${shortId(entry.id)} ${entry.scenario_name} ${entry.state}`}
                >
                  <span className="flex min-w-0 items-center gap-2 whitespace-nowrap">
                    <span className="mono shrink-0 text-info">{shortId(entry.id)}</span>
                    <span className="truncate">{entry.scenario_name}</span>
                    <RunStateBadge state={entry.state} size="xs" className="shrink-0" />
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : null}
      <div className="ml-auto flex items-center gap-2">
        <span className="panel-title text-[9px]">Demo speed</span>
        <Segmented
          value={String(demoSpeed)}
          onValueChange={(value) => setDemoSpeed(Number(value) as DemoSpeed)}
          options={SPEED_OPTIONS}
          ariaLabel="Demo simulation speed"
          size="xs"
        />
        <Button
          variant="primary"
          size="sm"
          onClick={startDemo}
          disabled={createRun.isPending || !demoAvailable || !mockOnline}
          title={
            demoAvailable
              ? mockOnline
                ? `Queue ${DEMO_SCENARIO} on the mock adapter`
                : "No runner currently advertises the mock adapter"
              : `The ${DEMO_SCENARIO} scenario is not in the library`
          }
        >
          <Play size={11} aria-hidden />
          {createRun.isPending ? "Queueing" : "Run demo scenario"}
        </Button>
      </div>
    </div>
  );

  if (system.isError) {
    return (
      <div className="p-4">
        <ErrorState
          title="Platform unavailable"
          error={system.error}
          onRetry={() => void system.refetch()}
        />
      </div>
    );
  }

  if (!selectedRunId) {
    return (
      <div className="flex flex-col gap-3 p-4">
        {toolbar}
        <Panel>
          <PanelBody>
            {runsQuery.isLoading ? (
              <LoadingPanel label="Looking for runs" />
            ) : (
              <EmptyState
                icon={Radar}
                title="No run on this platform yet"
                description={
                  runnerOnline
                    ? "Queue the demo scenario to see fault injection, propagation and recovery on the mock adapter."
                    : "No runner is online, so a new run would stay queued. Start a runner, then queue the demo scenario."
                }
                action={
                  <Button variant="primary" onClick={startDemo} disabled={!demoAvailable || !mockOnline}>
                    <Play size={11} aria-hidden />
                    Run demo scenario
                  </Button>
                }
              />
            )}
          </PanelBody>
        </Panel>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="flex flex-col gap-3 p-4">
        {toolbar}
        <Panel>
          <PanelBody>
            {connection === "error" ? (
              <EmptyState
                title="Run not available"
                description={streamError ?? "The run could not be opened for streaming."}
                action={
                  <Button asChild variant="outline">
                    <Link href="/runs">Browse runs</Link>
                  </Button>
                }
              />
            ) : (
              <LoadingPanel label="Connecting to the run stream" />
            )}
          </PanelBody>
        </Panel>
      </div>
    );
  }

  const canCancel = ACTIVE_RUN_STATES.includes(run.state) || run.state === "QUEUED";
  const metrics = metricsQuery.data ?? null;

  return (
    <div className="flex flex-col gap-2 p-2">
      {toolbar}

      <StatusBar
        run={run}
        adapter={adapter}
        connection={connection}
        simulationTime={simulationTime}
        progress={mission.progress}
        speed={run.speed}
        onCancel={() => cancelRun.mutate(run.id)}
        cancelPending={cancelRun.isPending}
        canCancel={canCancel}
        reportAvailable={reportAvailable || run.report_available}
      />

      {connection === "stale" ? (
        <Notice tone="warn">
          No frame received for more than 30 seconds while the run is active. The view may be behind
          the runner.
        </Notice>
      ) : null}
      {streamError && connection !== "closed" ? (
        <Notice tone="bad">{streamError}</Notice>
      ) : null}
      {run.state === "CANCELLED" ? (
        <Notice tone="warn">
          This run was cancelled{run.reason ? `: ${run.reason}.` : "."} Metrics are inconclusive.
        </Notice>
      ) : null}
      {run.state === "FAILED" ? (
        <Notice tone="bad">
          The run failed{run.reason ? `: ${run.reason}.` : "."} The analysis is inconclusive.
        </Notice>
      ) : null}

      <div className="grid h-[384px] grid-cols-[264px_minmax(300px,1fr)_330px] gap-2">
        <Panel aria-label="System">
          <PanelHeader>
            <PanelTitle>System</PanelTitle>
            <span className="ml-auto text-[10px] text-dim">{components.size} components</span>
          </PanelHeader>
          <PanelBody className="overflow-y-auto p-2">
            {system.isLoading ? (
              <LoadingPanel label="Loading topology" />
            ) : (
              <SystemPanel groups={groups} health={health} />
            )}
          </PanelBody>
        </Panel>

        <Panel aria-label="Digital twin">
          <PanelHeader>
            <PanelTitle>Digital twin</PanelTitle>
            <Badge tone="dim" size="xs" className="ml-auto">
              {adapter?.data_origin ?? run.adapter}
            </Badge>
          </PanelHeader>
          <PanelBody className="p-0">
            <DigitalTwin
              feed={feed}
              plannedPath={plannedPath ?? run.planned_path}
              cameraMode={cameraMode}
              onCameraModeChange={setCameraMode}
              reducedMotion={reducedMotion}
            />
          </PanelBody>
        </Panel>

        <div className="flex min-h-0 flex-col gap-2">
          <Panel aria-label="Active events" className="shrink-0">
            <PanelHeader>
              <PanelTitle>Active events</PanelTitle>
              <span className="ml-auto text-[10px] text-dim">{alerts.length} active</span>
            </PanelHeader>
            <PanelBody className="max-h-[88px] overflow-y-auto p-1.5">
              <ActiveAlerts alerts={alerts} />
            </PanelBody>
          </Panel>

          <Panel aria-label="Event feed" className="min-h-0 flex-1">
            <Tabs defaultValue="feed" className="flex min-h-0 flex-1 flex-col">
              <TabsList className="px-1">
                <TabsTrigger value="feed">Feed</TabsTrigger>
                <TabsTrigger value="upcoming">Upcoming</TabsTrigger>
                <TabsTrigger value="blast">Blast radius</TabsTrigger>
              </TabsList>
              <TabsContent value="feed" className="min-h-0 flex-1 overflow-y-auto">
                <EventLegend />
                <EventFeed events={feedEvents} emptyLabel="No events observed yet" dense />
              </TabsContent>
              <TabsContent value="upcoming" className="min-h-0 flex-1 overflow-y-auto">
                <UpcomingInjections
                  schedule={schedule}
                  now={simulationTime}
                  appliedIds={appliedIds}
                  names={names}
                />
              </TabsContent>
              <TabsContent value="blast" className="min-h-0 flex-1 overflow-y-auto p-2">
                <BlastRadius
                  components={components}
                  injected={new Set(containment.injectedComponents)}
                  affected={new Set(containment.affectedComponents)}
                  health={health}
                  boundary={boundary}
                  affectedDomains={containment.affectedDomains}
                  flightDomainAffected={containment.flightDomainAffected}
                />
              </TabsContent>
            </Tabs>
          </Panel>
        </div>
      </div>

      <Panel aria-label="System state timeline">
        <PanelHeader>
          <PanelTitle>System state timeline</PanelTitle>
          <span className="ml-auto text-[10px] text-dim">
            {tracks.length} observed subsystems, {markers.length} injections applied
          </span>
        </PanelHeader>
        <PanelBody className="max-h-[152px] overflow-y-auto overflow-x-hidden p-1.5">
          {tracks.length === 0 ? (
            <p className="px-1 py-4 text-[12px] text-muted">
              No subsystem state change observed yet.
            </p>
          ) : (
            <StateTimeline
              tracks={tracks}
              markers={markers}
              now={simulationTime}
              duration={Math.max(simulationTime, run.last_simulation_time, 1)}
            />
          )}
        </PanelBody>
      </Panel>

      <div className="grid grid-cols-4 gap-2">
        <MissionKpi live={mission} metrics={metrics} />
        <RecoveryKpi live={recovery} metrics={metrics} />
        <ContainmentKpi live={containment} metrics={metrics} />
        {metrics ? (
          <ScoreKpi metrics={metrics} runId={run.id} reportAvailable={run.report_available} />
        ) : (
          <Panel>
            <PanelHeader>
              <PanelTitle>Resilience score</PanelTitle>
            </PanelHeader>
            <PanelBody className="flex flex-col gap-1 p-2">
              <p className="kpi-value text-[20px] text-dim">--</p>
              <p className="text-[11.5px] leading-snug text-muted">
                {run.state === "COMPLETED"
                  ? "The analysis is not available for this run."
                  : terminal
                    ? "This run did not complete, so the result is inconclusive and no score is produced."
                    : "The score is computed once the run completes and the analysis finishes."}
              </p>
            </PanelBody>
          </Panel>
        )}
      </div>
    </div>
  );
}

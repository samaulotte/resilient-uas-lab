"use client";

import Link from "next/link";

import { Badge, ResultBadge } from "@/components/ui/badge";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { InfoTip } from "@/components/ui/tooltip";
import { formatScore } from "@/lib/format";
import type { LiveContainmentKpis, LiveMissionKpis, LiveRecoveryKpis } from "@/lib/run-view";
import { DOMAIN_ORDER, FLIGHT_MODE, TONE_TEXT, type Tone } from "@/lib/states";
import { cn, formatDuration, formatPercent } from "@/lib/utils";
import type { MetricsResponse } from "@reslab/api-client";

function KpiPanel({
  title,
  analyzed,
  children,
  info,
}: {
  title: string;
  analyzed: boolean;
  children: React.ReactNode;
  info?: React.ReactNode;
}) {
  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>{title}</PanelTitle>
        {info ? <InfoTip label={`About ${title}`}>{info}</InfoTip> : null}
        <Badge tone={analyzed ? "info" : "dim"} size="xs" className="ml-auto">
          {analyzed ? "ANALYZED" : "LIVE ESTIMATE"}
        </Badge>
      </PanelHeader>
      <PanelBody className="flex flex-col gap-1 p-2">{children}</PanelBody>
    </Panel>
  );
}

function KpiValue({ value, tone }: { value: string; tone?: Tone }) {
  return (
    <p className={cn("kpi-value text-[20px]", tone ? TONE_TEXT[tone] : "text-foreground")}>
      {value}
    </p>
  );
}

function KpiRowItem({ label, value, tone }: { label: string; value: string; tone?: Tone }) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-[11.5px]">
      <span className="text-muted">{label}</span>
      <span className={cn("mono", tone ? TONE_TEXT[tone] : "text-foreground")}>{value}</span>
    </div>
  );
}

export function MissionKpi({
  live,
  metrics,
}: {
  live: LiveMissionKpis;
  metrics: MetricsResponse | null;
}) {
  const analyzed = metrics !== null;
  const completion = analyzed ? metrics.metrics.mission.completion : live.progress;
  const preserved = analyzed ? metrics.metrics.safety.preserved : live.safetyPreserved;
  return (
    <KpiPanel
      title="Mission"
      analyzed={analyzed}
      info="Mission progress and the safety state of the vehicle. Safety is preserved while the flight core keeps full control authority and never leaves a healthy state."
    >
      <KpiValue value={formatPercent(completion, 0)} />
      <KpiRowItem label="Phase" value={live.phase} />
      <KpiRowItem
        label="Flight mode"
        value={FLIGHT_MODE[live.flightMode as keyof typeof FLIGHT_MODE]?.label ?? live.flightMode}
        tone={FLIGHT_MODE[live.flightMode as keyof typeof FLIGHT_MODE]?.tone}
      />
      <KpiRowItem label="Autonomy" value={live.autonomy} />
      <div className="flex items-center justify-between gap-2 pt-0.5 text-[11.5px]">
        <span className="text-muted">Safety state</span>
        {!analyzed && !live.observed ? (
          <Badge tone="dim" size="xs" title="Nothing was observed for this run">
            NO OBSERVATION
          </Badge>
        ) : (
          <Badge tone={preserved ? "ok" : "bad"} size="xs">
            {preserved ? "PRESERVED" : "VIOLATED"}
          </Badge>
        )}
      </div>
    </KpiPanel>
  );
}

export function RecoveryKpi({
  live,
  metrics,
}: {
  live: LiveRecoveryKpis;
  metrics: MetricsResponse | null;
}) {
  const analyzed = metrics !== null;
  const recovered = analyzed ? metrics.metrics.recovery.faults_recovered : live.recovered;
  const required = analyzed
    ? metrics.metrics.recovery.faults_requiring_recovery
    : live.faultsObserved;
  const mttr = analyzed ? metrics.metrics.recovery.mean_time_to_recovery : live.meanTimeToRecovery;
  const safeState = analyzed ? metrics.metrics.recovery.time_to_safe_state : live.timeToSafeState;
  const entered = analyzed ? metrics.metrics.recovery.safe_state_entered : live.safeStateEntered;
  return (
    <KpiPanel
      title="Recovery"
      analyzed={analyzed}
      info="How many observed faults returned to a healthy state, and how long that took. The live estimate uses the fault duration reported with each recovery event."
    >
      <KpiValue
        value={`${recovered} / ${required}`}
        tone={required === 0 ? "dim" : recovered === required ? "ok" : "warn"}
      />
      <KpiRowItem label="Recovered / observed faults" value={`${recovered} of ${required}`} />
      <KpiRowItem
        label="Mean time to recovery"
        value={mttr !== null ? formatDuration(mttr) : "n/a"}
      />
      <KpiRowItem
        label="Time to safe state"
        value={
          entered && safeState !== null
            ? formatDuration(safeState)
            : entered
              ? "entered"
              : "not entered"
        }
        tone={entered ? "warn" : "dim"}
      />
    </KpiPanel>
  );
}

export function ContainmentKpi({
  live,
  metrics,
}: {
  live: LiveContainmentKpis;
  metrics: MetricsResponse | null;
}) {
  const analyzed = metrics !== null;
  const propagation = metrics?.metrics.propagation;
  const contained = analyzed ? (propagation?.contained ?? true) : live.contained;
  const flightAffected = analyzed
    ? (propagation?.flight_domain_affected ?? false)
    : live.flightDomainAffected;
  const affectedDomains = analyzed
    ? (propagation?.affected_domains.length ?? 0)
    : live.affectedDomains.length;
  const propagated = analyzed
    ? (propagation?.propagated_components.length ?? 0)
    : live.propagatedComponents.length;
  return (
    <KpiPanel
      title="Containment"
      analyzed={analyzed}
      info="Blast radius of the injected faults. A run is contained while no fault reaches the flight-critical domain (flight control or actuation)."
    >
      {!analyzed && live.affectedComponents.length === 0 ? (
        <KpiValue value="NO FAULT" tone="dim" />
      ) : (
        <KpiValue value={contained ? "CONTAINED" : "PROPAGATED"} tone={contained ? "ok" : "bad"} />
      )}
      <KpiRowItem label="Affected domains" value={`${affectedDomains} / ${DOMAIN_ORDER.length}`} />
      <KpiRowItem label="Propagated components" value={String(propagated)} />
      <div className="flex items-center justify-between gap-2 pt-0.5 text-[11.5px]">
        <span className="text-muted">Flight domain</span>
        <Badge tone={flightAffected ? "bad" : "ok"} size="xs">
          {flightAffected ? "AFFECTED" : "UNTOUCHED"}
        </Badge>
      </div>
    </KpiPanel>
  );
}

export function ScoreKpi({
  metrics,
  runId,
  reportAvailable,
}: {
  metrics: MetricsResponse;
  runId: string;
  reportAvailable: boolean;
}) {
  const score = metrics.score;
  const gatesPassed = score.hard_gates.every((gate) => gate.passed);
  return (
    <KpiPanel
      title="Resilience score"
      analyzed
      info="Weighted score over the profile dimensions, on a 0 to 100 scale. Hard gates override the number: a violated critical assertion or a loss of control fails the run whatever the score."
    >
      <div className="flex items-baseline gap-2" data-testid="resilience-score">
        <KpiValue value={formatScore(score.total)} />
        <ResultBadge result={score.result} size="sm" />
      </div>
      <KpiRowItem
        label="Hard gates"
        value={gatesPassed ? "all passed" : "violated"}
        tone={gatesPassed ? "ok" : "bad"}
      />
      <KpiRowItem label="Profile" value={score.profile.name} />
      <div className="flex items-center gap-2 pt-0.5 text-[11.5px]">
        <Link href={`/runs/${runId}`} className="text-info hover:underline">
          Run analysis
        </Link>
        {reportAvailable ? (
          <Link href={`/reports?run=${runId}`} className="text-info hover:underline">
            Report
          </Link>
        ) : null}
      </div>
    </KpiPanel>
  );
}

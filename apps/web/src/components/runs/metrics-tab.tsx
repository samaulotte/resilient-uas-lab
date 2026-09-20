"use client";

import { Badge } from "@/components/ui/badge";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/components/ui/panel";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { InfoTip } from "@/components/ui/tooltip";
import { COMPONENT_STATE } from "@/lib/states";
import { cn, formatDuration, formatMissionTime, formatPercent } from "@/lib/utils";
import type { MetricsResult, RecoveryRecord } from "@reslab/api-client";

interface MetricRowSpec {
  label: string;
  value: string;
  definition: string;
  tone?: "ok" | "warn" | "bad";
}

function MetricGroup({ title, rows }: { title: string; rows: readonly MetricRowSpec[] }) {
  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>{title}</PanelTitle>
      </PanelHeader>
      <PanelBody className="p-0">
        <ul className="divide-y divide-border">
          {rows.map((row) => (
            <li key={row.label} className="flex items-center justify-between gap-2 px-3 py-1.5">
              <span className="flex items-center gap-1 text-[11.5px] text-muted">
                {row.label}
                <InfoTip label={`Definition of ${row.label}`}>{row.definition}</InfoTip>
              </span>
              <span
                className={cn(
                  "mono text-[12px]",
                  row.tone === "ok" && "text-ok",
                  row.tone === "warn" && "text-warn",
                  row.tone === "bad" && "text-bad",
                  !row.tone && "text-foreground",
                )}
              >
                {row.value}
              </span>
            </li>
          ))}
        </ul>
      </PanelBody>
    </Panel>
  );
}

function bool(value: boolean): string {
  return value ? "yes" : "no";
}

function optionalSeconds(value: number | null): string {
  return value === null ? "n/a" : formatDuration(value);
}

export function MetricsTab({ metrics }: { metrics: MetricsResult }) {
  const { mission, availability, recovery, propagation, modes, safety, events } = metrics;
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-3">
        <MetricGroup
          title="Mission"
          rows={[
            {
              label: "Completion",
              value: formatPercent(mission.completion),
              definition: "Highest mission progress ratio observed in telemetry.",
            },
            {
              label: "Continuity",
              value: formatPercent(mission.continuity),
              definition:
                "1 minus the fraction of the run spent holding or diverted, from the observed flight mode and mission phase.",
            },
            {
              label: "Completed",
              value: bool(mission.completed),
              definition: "True when the last telemetry sample reports the COMPLETE mission phase.",
              tone: mission.completed ? "ok" : "warn",
            },
            {
              label: "Duration",
              value: formatDuration(mission.duration),
              definition: "Simulation seconds between the first and the last telemetry sample.",
            },
            {
              label: "Time in hold",
              value: formatDuration(mission.time_in_hold),
              definition: "Time spent in HOLD or RTL, or in the HOLDING mission phase.",
            },
            {
              label: "Time in mission modes",
              value: formatDuration(mission.time_in_mission_modes),
              definition: "Time spent in MISSION, TAKEOFF or LAND.",
            },
          ]}
        />
        <MetricGroup
          title="Availability"
          rows={[
            {
              label: "Control",
              value: formatPercent(availability.control),
              definition:
                "Fraction of the run during which the flight core was in a healthy state.",
            },
            {
              label: "Navigation integrity",
              value: formatPercent(availability.navigation_integrity),
              definition:
                "Weighted navigation estimator availability: healthy counts 1.0, degraded 0.5, down 0.0.",
            },
            {
              label: "Navigation",
              value: formatPercent(availability.navigation),
              definition: "Fraction of the run with a healthy navigation estimator.",
            },
            {
              label: "Communications",
              value: formatPercent(availability.communications),
              definition: "Fraction of the run with every communications component healthy.",
            },
            {
              label: "Compute",
              value: formatPercent(availability.compute),
              definition: "Fraction of the run with every mission compute component healthy.",
            },
            {
              label: "Power",
              value: formatPercent(availability.power),
              definition: "Fraction of the run with every power component healthy.",
            },
          ]}
        />
        <MetricGroup
          title="Safety"
          rows={[
            {
              label: "Preserved",
              value: bool(safety.preserved),
              definition:
                "No loss of control and the flight core never left a healthy state during the run.",
              tone: safety.preserved ? "ok" : "bad",
            },
            {
              label: "Loss of control",
              value: bool(safety.loss_of_control),
              definition:
                "A sample reported the flight core without control authority, or in the FAILED state.",
              tone: safety.loss_of_control ? "bad" : "ok",
            },
            {
              label: "Flight control available",
              value: bool(safety.flight_control_available),
              definition: "The flight core spent no time in a non-healthy state.",
              tone: safety.flight_control_available ? "ok" : "bad",
            },
            {
              label: "Control availability",
              value: formatPercent(safety.control_availability),
              definition: "Same as the control availability metric, repeated for the safety case.",
            },
            {
              label: "Safe state reached",
              value: bool(safety.safe_state_reached),
              definition:
                "A system response event flagged as a safe state (failsafe hold, return to launch) was observed.",
              tone: safety.safe_state_reached ? "warn" : "ok",
            },
          ]}
        />
        <MetricGroup
          title="Recovery"
          rows={[
            {
              label: "Mean time to recovery",
              value: optionalSeconds(recovery.mean_time_to_recovery),
              definition:
                "Average time from the end of the disturbance to the return to a healthy state, over the faults that recovered.",
            },
            {
              label: "Max time to recovery",
              value: optionalSeconds(recovery.max_time_to_recovery),
              definition: "Slowest recovery observed in the run.",
            },
            {
              label: "Faults requiring recovery",
              value: String(recovery.faults_requiring_recovery),
              definition:
                "Observed faults whose disturbance ended during the run, so a recovery was expected.",
            },
            {
              label: "Faults recovered",
              value: String(recovery.faults_recovered),
              definition: "Faults that returned to a healthy state.",
            },
            {
              label: "Success rate",
              value:
                recovery.success_rate === null ? "n/a" : formatPercent(recovery.success_rate, 0),
              definition:
                "Recovered divided by required; not defined when no recovery was required.",
            },
            {
              label: "Time to safe state",
              value: optionalSeconds(recovery.time_to_safe_state),
              definition:
                "Seconds from the observed fault that triggered the first safe-state response to that response.",
            },
          ]}
        />
        <MetricGroup
          title="Propagation"
          rows={[
            {
              label: "Contained",
              value: bool(propagation.contained),
              definition: "No fault reached the flight-critical domain.",
              tone: propagation.contained ? "ok" : "bad",
            },
            {
              label: "Injected components",
              value: String(propagation.injected_components.length),
              definition: "Components an injection was applied to by the adapter.",
            },
            {
              label: "Affected components",
              value: String(propagation.affected_components.length),
              definition: "Components observed leaving a healthy state.",
            },
            {
              label: "Propagated components",
              value: String(propagation.propagated_components.length),
              definition: "Affected components that were not themselves injection targets.",
            },
            {
              label: "Max propagation depth",
              value: String(propagation.max_propagation_depth),
              definition:
                "Longest dependency distance from an injection target to an affected component.",
            },
            {
              label: "Trust boundary crossed",
              value: bool(propagation.boundary_crossed),
              definition:
                "A dependency marked as crossing a trust boundary had both ends affected.",
              tone: propagation.boundary_crossed ? "bad" : "ok",
            },
          ]}
        />
        <MetricGroup
          title="System modes and events"
          rows={[
            {
              label: "Time nominal",
              value: formatDuration(modes.time_nominal),
              definition: "Time with every observed component healthy.",
            },
            {
              label: "Time degraded",
              value: formatDuration(modes.time_degraded),
              definition:
                "Time with at least one impaired component but no failure and no flight-critical loss.",
            },
            {
              label: "Time failed",
              value: formatDuration(modes.time_failed),
              definition: "Time with a failed component or a flight-critical component down.",
              tone: modes.time_failed > 0 ? "bad" : undefined,
            },
            {
              label: "Injections requested / applied",
              value: `${events.injected} / ${events.applied}`,
              definition:
                "A requested injection is not evidence of a disturbance; only an applied injection was confirmed by the adapter.",
            },
            {
              label: "Observed effects",
              value: String(events.observed_effects),
              definition: "Component state changes observed in the target.",
            },
            {
              label: "Expectations passed / failed",
              value: `${events.expectations_passed} / ${events.expectations_failed}`,
              definition: "Declared expectations of the scenario checked against observations.",
              tone: events.expectations_failed > 0 ? "bad" : undefined,
            },
          ]}
        />
      </div>

      <Panel>
        <PanelHeader>
          <PanelTitle>Recovery records</PanelTitle>
          <span className="ml-auto text-[10px] text-dim">{recovery.records.length} records</span>
        </PanelHeader>
        <PanelBody className="p-0">
          <RecoveryRecords records={recovery.records} />
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Final component states</PanelTitle>
        </PanelHeader>
        <PanelBody className="p-0">
          <Table>
            <THead>
              <tr>
                <TH>Component</TH>
                <TH>Final state</TH>
                <TH>Time in state</TH>
              </tr>
            </THead>
            <TBody>
              {Object.entries(metrics.final_component_states)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([component, state]) => {
                  const times = metrics.component_time_in_state[component] ?? {};
                  return (
                    <TR key={component}>
                      <TD className="mono">{component}</TD>
                      <TD>
                        <Badge tone={COMPONENT_STATE[state].tone} size="xs">
                          {COMPONENT_STATE[state].label}
                        </Badge>
                      </TD>
                      <TD className="text-muted">
                        {Object.entries(times)
                          .filter(([, seconds]) => seconds > 0)
                          .map(([name, seconds]) => `${name} ${formatDuration(seconds)}`)
                          .join(", ") || "no transition"}
                      </TD>
                    </TR>
                  );
                })}
            </TBody>
          </Table>
        </PanelBody>
      </Panel>
    </div>
  );
}

function RecoveryRecords({ records }: { records: readonly RecoveryRecord[] }) {
  if (records.length === 0) {
    return <p className="px-3 py-4 text-[12px] text-muted">No fault was observed in this run.</p>;
  }
  return (
    <Table>
      <THead>
        <tr>
          <TH>Subsystem</TH>
          <TH>Fault state</TH>
          <TH>Attribution</TH>
          <TH>Caused by</TH>
          <TH className="text-right">Fault start</TH>
          <TH className="text-right">Recovered</TH>
          <TH className="text-right">Fault duration</TH>
          <TH className="text-right">Recovery time</TH>
          <TH>Expected</TH>
        </tr>
      </THead>
      <TBody>
        {records.map((record, index) => (
          <TR key={`${record.subsystem}-${index}`}>
            <TD className="mono">{record.subsystem}</TD>
            <TD>
              <Badge tone={COMPONENT_STATE[record.fault_state].tone} size="xs">
                {COMPONENT_STATE[record.fault_state].label}
              </Badge>
            </TD>
            <TD>
              <Badge tone={record.direct ? "info" : "warn"} size="xs">
                {record.direct ? "DIRECT" : "PROPAGATED"}
              </Badge>
            </TD>
            <TD className="mono text-muted">{record.caused_by ?? "-"}</TD>
            <TD className="mono text-right">{formatMissionTime(record.fault_started_at)}</TD>
            <TD className="mono text-right">
              {record.recovered_at === null ? "-" : formatMissionTime(record.recovered_at)}
            </TD>
            <TD className="mono text-right">{optionalSeconds(record.fault_duration)}</TD>
            <TD className="mono text-right">{optionalSeconds(record.recovery_time)}</TD>
            <TD className="text-muted">
              {record.recovery_expected ? "yes" : "no, disturbance held to the end"}
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
